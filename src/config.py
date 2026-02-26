"""Configuration module for Rabbit-Quant.

Loads settings from .env (via Pydantic Settings) and TOML files (asset lists,
strategy params, timeframe mappings). All other modules import config from here.
"""

import sys
from pathlib import Path

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings

# Project root is the parent of src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

# TOML loading: stdlib tomllib on 3.11+, tomli on 3.10
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError as e:
        raise ImportError("Install tomli for Python < 3.11: uv add tomli") from e


def _load_toml(filename: str) -> dict:
    """Load a TOML file from the config directory."""
    path = CONFIG_DIR / filename
    if not path.exists():
        logger.warning(f"Config file not found: {path}")
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


class AppSettings(BaseSettings):
    """Environment-based settings loaded from .env file."""

    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    # Database
    duckdb_path: str = Field(default="data/rabbit.duckdb", description="Path to DuckDB database file")

    # Postgres (Optional)
    database_host: str = Field(default="", description="Postgres Host")
    database_port: int = Field(default=5432, description="Postgres Port")
    database_name: str = Field(default="", description="Postgres DB Name")
    database_user: str = Field(default="", description="Postgres User")
    database_password: str = Field(default="", description="Postgres Password")

    @property
    def use_postgres(self) -> bool:
        return bool(self.database_host and self.database_name and self.database_user)

    @property
    def database_url(self) -> str:
        if not self.use_postgres:
            return ""
        return f"postgresql://{self.database_user}:{self.database_password}@{self.database_host}:{self.database_port}/{self.database_name}"

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_path: str = Field(default="logs/rabbit.log", description="Log file path")

    # Data source
    yfinance_proxy: str = Field(default="", description="Proxy for yfinance requests")

    # Notifications
    telegram_bot_token: str = Field(default="", description="Telegram Bot Token for alerts")
    telegram_chat_id: str = Field(default="", description="Telegram Chat ID for alerts")


class AssetConfig:
    """Asset lists loaded from config/assets.toml."""

    def __init__(self) -> None:
        data = _load_toml("assets.toml")
        self.stock_symbols: list[str] = data.get("stocks", {}).get("symbols", [])
        self.crypto_symbols: list[str] = data.get("crypto", {}).get("symbols", [])
        self.crypto_exchange: str = data.get("crypto", {}).get("exchange", "binance")

    @property
    def all_symbols(self) -> list[str]:
        return self.stock_symbols + self.crypto_symbols


class StrategyConfig:
    """Strategy parameters loaded from config/strategy.toml."""

    def __init__(self) -> None:
        data = _load_toml("strategy.toml")
        hurst = data.get("hurst", {})
        cycle = data.get("cycle", {})
        backtest = data.get("backtest", {})

        # Hurst settings
        self.hurst_threshold: float = hurst.get("threshold", 0.6)
        self.hurst_min_data_points: int = hurst.get("min_data_points", 256)

        # Cycle settings
        self.cycle_min_period: int = cycle.get("min_period", 10)
        self.cycle_max_period: int = cycle.get("max_period", 200)
        self.cycle_projection_bars: int = cycle.get("projection_bars", 20)
        self.cycle_lowpass_cutoff: float = cycle.get("lowpass_cutoff", 0.1)

        # Filter settings
        filters = data.get("filters", {})
        self.macro_filter_type: str = filters.get("macro_filter_type", "both")
        self.htf_threshold: float = filters.get("htf_threshold", 50.0)
        self.ltf_threshold: float = filters.get("ltf_threshold", 50.0)
        self.veto_threshold: float = filters.get("veto_threshold", 3.0)

        # Backtest settings
        self.backtest_hurst_range: list[float] = backtest.get("hurst_range", [0.5, 0.6, 0.7, 0.8, 0.9])
        self.backtest_phase_long_range: list[float] = backtest.get("phase_long_range", [4.0, 4.4, 4.712, 5.0, 5.5])
        self.backtest_phase_short_range: list[float] = backtest.get("phase_short_range", [1.0, 1.3, 1.571, 1.8, 2.1])
        self.backtest_initial_capital: float = backtest.get("initial_capital", 100000.0)
        self.backtest_commission: float = backtest.get("commission", 0.001)
        self.backtest_output_dir: str = backtest.get("output_dir", "data/backtest")
        self.backtest_trailing_atr_multiplier_range: list[float] = backtest.get("trailing_atr_multiplier_range", [1.5, 2.0, 2.5, 3.0])

        # Risk settings
        risk = data.get("risk", {})
        self.risk_per_trade: float = risk.get("risk_per_trade", 0.02)
        self.trailing_atr_multiplier: float = risk.get("trailing_atr_multiplier", 3.0)
        self.breakeven_atr_threshold: float = risk.get("breakeven_atr_threshold", 2.0)
        self.max_portfolio_exposure: float = risk.get("max_portfolio_exposure", 0.06)
        self.max_concurrent_trades: int = risk.get("max_concurrent_trades", 3)


class PaperConfig:
    """Paper trading parameters loaded from config/strategy.toml."""

    def __init__(self) -> None:
        data = _load_toml("strategy.toml")
        paper = data.get("paper", {})
        self.initial_balance: float = paper.get("initial_balance", 10000.0)
        self.fixed_position_size: float = paper.get("fixed_position_size", 1000.0)
        self.use_dynamic_sizing: bool = paper.get("use_dynamic_sizing", False)


class TimeframeConfig:
    """Timeframe mappings loaded from config/timeframes.toml."""

    def __init__(self) -> None:
        data = _load_toml("timeframes.toml")
        self.default_timeframes: list[str] = data.get("timeframes", {}).get("default", ["1m", "5m", "15m", "1h", "4h", "1d"])
        self.yfinance_mapping: dict[str, str] = data.get("yfinance_mapping", {})
        self.ccxt_mapping: dict[str, str] = data.get("ccxt_mapping", {})


def setup_logging(settings: AppSettings) -> None:
    """Configure loguru logging with file rotation."""
    log_path = PROJECT_ROOT / settings.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )
    logger.add(
        str(log_path),
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function} - {message}",
    )


def load_config() -> tuple[AppSettings, AssetConfig, StrategyConfig, TimeframeConfig, PaperConfig]:
    """Load all configuration. Call once at startup."""
    settings = AppSettings()
    setup_logging(settings)
    assets = AssetConfig()
    strategy = StrategyConfig()
    timeframes = TimeframeConfig()
    paper = PaperConfig()
    logger.info("Configuration loaded successfully")
    return settings, assets, strategy, timeframes, paper
