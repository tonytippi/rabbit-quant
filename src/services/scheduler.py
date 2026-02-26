"""Writer Service: Standalone scheduler for background data ingestion.

Handles periodic fetching of OHLCV data for all configured assets,
owning the DuckDB write lock to avoid conflicts with reader apps.
"""

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.config import AppSettings, AssetConfig, PaperConfig, TimeframeConfig
from src.data_loader import get_connection, query_ohlcv
from src.fetchers.orchestrator import fetch_all_assets
from src.services.notifier import TelegramNotifier
from src.services.trader import PaperTrader
from src.signals.filters import generate_signal


class IngestionScheduler:
    """Orchestrates periodic market data fetching."""

    def __init__(
        self,
        settings: AppSettings,
        assets: AssetConfig,
        timeframes: TimeframeConfig,
        paper_config: PaperConfig,
        interval_minutes: int = 5,
    ) -> None:
        self.settings = settings
        self.assets = assets
        self.timeframes = timeframes
        self.paper_config = paper_config
        self.interval_minutes = interval_minutes
        self.scheduler = AsyncIOScheduler()
        self.notifier = TelegramNotifier(settings)

        # Configure separate logger for signals
        logger.add("logs/trading_signals.log", filter=lambda record: "SIGNAL" in record["extra"], rotation="1 MB")

    async def _fetch_job(self) -> None:
        """Single fetch cycle."""
        logger.info("Executing scheduled fetch job...")
        conn = get_connection(self.settings, read_only=False)
        trader = PaperTrader(conn, self.paper_config)

        try:
            # 1. Fetch Data
            result = await fetch_all_assets(conn, self.assets, self.timeframes)
            logger.info(f"Scheduled fetch complete: {result.rows_upserted} rows upserted")

            # 2. Monitor Existing Positions (Exit Logic)
            # We need current prices. Let's fetch latest close for all symbols from DB.
            current_prices = {}
            for symbol in self.assets.all_symbols:
                # Get latest price from 1m or 5m or just whatever we have most recent
                # We'll use the smallest timeframe available for best price accuracy
                tf = self.timeframes.default_timeframes[0] # e.g. 1m
                df = query_ohlcv(conn, symbol, tf, limit=1)
                if not df.empty:
                    current_prices[symbol] = float(df["close_price"].iloc[-1])

            if current_prices:
                trader.monitor_positions(current_prices)

            # 3. Scan for New Signals (Entry Logic)
            await self._scan_signals(conn, trader)

        except Exception as e:
            logger.error(f"Scheduled fetch failed: {e}")
        finally:
            conn.close()

    async def _scan_signals(self, conn, trader: PaperTrader) -> None:
        """Scan all assets for trading signals and log them."""
        logger.info("Scanning for trading signals...")

        # Determine strategy config (load lazily or pass in init)
        from src.config import StrategyConfig
        strategy = StrategyConfig()

        symbols = self.assets.all_symbols
        timeframes = self.timeframes.default_timeframes

        signal_count = 0

        for symbol in symbols:
            for tf in timeframes:
                try:
                    df = query_ohlcv(conn, symbol, tf, limit=500)
                    if df.empty or len(df) < strategy.hurst_min_data_points:
                        continue

                    # Use shared signal generation logic
                    result = generate_signal(
                        df, symbol, tf,
                        hurst_threshold=strategy.hurst_threshold,
                        lowpass_cutoff=strategy.cycle_lowpass_cutoff
                    )

                    if result and result["signal"] in ["long", "short"]:
                        signal = result["signal"]
                        price = df["close_price"].iloc[-1]
                        hurst = result["hurst_value"]
                        phase = result["current_phase"]
                        tp = result.get("tp", 0.0)
                        sl = result.get("sl", 0.0)

                        # Prepare signal data for trader
                        signal_data = {
                            "symbol": symbol,
                            "timeframe": tf,
                            "signal": signal,
                            "price": price,
                            "tp": tp,
                            "sl": sl
                        }

                        # Execute Trade (Paper)
                        if trader.open_position(signal_data):
                            logger.info(f"Paper Trade Opened: {symbol} {signal}")

                        # Log signal
                        log_msg = (
                            f"🚨 {signal.upper()} SIGNAL: {symbol} [{tf}] @ {price:.2f} | "
                            f"TP: {tp:.2f} | SL: {sl:.2f} | Hurst: {hurst:.2f}"
                        )
                        logger.bind(SIGNAL=True).info(log_msg)
                        signal_count += 1

                        # Send Telegram alert
                        emoji = "🟢" if signal == "long" else "🔴"
                        tg_msg = (
                            f"{emoji} *{signal.upper()} SIGNAL*\n"
                            f"**Asset:** `{symbol}`\n"
                            f"**TF:** `{tf}`\n"
                            f"**Price:** `{price:.2f}`\n"
                            f"**TP:** `{tp:.2f}`\n"
                            f"**SL:** `{sl:.2f}`\n"
                            f"**Hurst:** `{hurst:.2f}`"
                        )
                        await self.notifier.send(tg_msg)

                except Exception as e:
                    logger.error(f"Signal scan error for {symbol}/{tf}: {e}")

        logger.info(f"Signal scan complete. Found {signal_count} opportunities.")

    async def start(self) -> None:
        """Start the persistent scheduler loop."""
        logger.info(f"Starting Writer Service (Interval: {self.interval_minutes}m)...")

        # Schedule the job
        self.scheduler.add_job(
            self._fetch_job,
            "interval",
            minutes=self.interval_minutes,
            id="market_data_fetch"
        )

        # Trigger first run immediately
        await self._fetch_job()

        self.scheduler.start()

        # Keep alive
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Writer Service stopping...")
            self.scheduler.shutdown()


async def run_scheduler_service(
    settings: AppSettings,
    assets: AssetConfig,
    timeframes: TimeframeConfig,
    paper_config: PaperConfig,
    interval: int = 5
) -> None:
    """Entry point for the scheduler process."""
    service = IngestionScheduler(settings, assets, timeframes, paper_config, interval_minutes=interval)
    await service.start()
