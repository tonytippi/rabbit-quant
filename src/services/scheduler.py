"""Writer Service: Standalone scheduler for background data ingestion.

Handles periodic fetching of OHLCV data for all configured assets,
owning the DuckDB write lock to avoid conflicts with reader apps.
"""

import asyncio
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from src.config import AppSettings, AssetConfig, TimeframeConfig
from src.data_loader import get_connection, query_ohlcv
from src.fetchers.orchestrator import fetch_all_assets
from src.signals.cycles import detect_dominant_cycle_filtered
from src.signals.fractals import calculate_hurst
from src.signals.filters import _determine_signal
from src.services.notifier import TelegramNotifier


class IngestionScheduler:
    """Orchestrates periodic market data fetching."""

    def __init__(
        self,
        settings: AppSettings,
        assets: AssetConfig,
        timeframes: TimeframeConfig,
        interval_minutes: int = 5,
    ) -> None:
        self.settings = settings
        self.assets = assets
        self.timeframes = timeframes
        self.interval_minutes = interval_minutes
        self.scheduler = AsyncIOScheduler()
        self.notifier = TelegramNotifier(settings)
        
        # Configure separate logger for signals
        logger.add("logs/trading_signals.log", filter=lambda record: "SIGNAL" in record["extra"], rotation="1 MB")

    async def _fetch_job(self) -> None:
        """Single fetch cycle."""
        logger.info("Executing scheduled fetch job...")
        conn = get_connection(self.settings, read_only=False)
        try:
            result = await fetch_all_assets(conn, self.assets, self.timeframes)
            logger.info(f"Scheduled fetch complete: {result.rows_upserted} rows upserted")
            
            # Run signal scan immediately after fetch
            await self._scan_signals(conn)
            
        except Exception as e:
            logger.error(f"Scheduled fetch failed: {e}")
        finally:
            conn.close()

    async def _scan_signals(self, conn) -> None:
        """Scan all assets for trading signals and log them."""
        logger.info("Scanning for trading signals...")
        
        # Determine strategy config (load lazily or pass in init)
        # For now we use defaults or load from toml if needed
        from src.config import StrategyConfig
        strategy = StrategyConfig()
        
        symbols = self.assets.all_symbols
        timeframes = self.timeframes.default_timeframes
        
        signal_count = 0
        
        for symbol in symbols:
            for tf in timeframes:
                try:
                    df = query_ohlcv(conn, symbol, tf, limit=500) # Fetch enough for signal
                    if df.empty or len(df) < strategy.hurst_min_data_points:
                        continue
                        
                    # Compute signals
                    hurst = calculate_hurst(df)
                    cycle = detect_dominant_cycle_filtered(df, cutoff=strategy.cycle_lowpass_cutoff)
                    
                    if cycle:
                        signal = _determine_signal(
                            cycle["current_phase"], 
                            hurst, 
                            strategy.hurst_threshold
                        )
                        
                        if signal in ["long", "short"]:
                            price = df["close_price"].iloc[-1]
                            # Log signal
                            log_msg = (
                                f"🚨 {signal.upper()} SIGNAL detected: {symbol} [{tf}] @ {price:.2f} "
                                f"(Hurst={hurst:.2f}, Phase={cycle['current_phase']:.2f})"
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
                                f"**Hurst:** `{hurst:.2f}`\n"
                                f"**Phase:** `{cycle['current_phase']:.2f}`"
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
    interval: int = 5
) -> None:
    """Entry point for the scheduler process."""
    service = IngestionScheduler(settings, assets, timeframes, interval_minutes=interval)
    await service.start()
