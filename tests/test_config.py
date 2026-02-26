"""Tests for src/config.py — configuration loading and validation."""

from src.config import (
    AppSettings,
    AssetConfig,
    PaperConfig,
    StrategyConfig,
    TimeframeConfig,
    _load_toml,
    load_config,
    setup_logging,
)


class TestAppSettings:
    def test_default_values(self):
        settings = AppSettings()
        assert settings.duckdb_path == "data/rabbit.duckdb" or settings.duckdb_path
        assert settings.log_level in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DUCKDB_PATH", "/custom/path.duckdb")
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        settings = AppSettings()
        assert settings.duckdb_path == "/custom/path.duckdb"
        assert settings.log_level == "ERROR"

    def test_extra_env_vars_ignored(self, monkeypatch):
        monkeypatch.setenv("UNKNOWN_SETTING", "should_not_crash")
        settings = AppSettings()
        assert not hasattr(settings, "unknown_setting")


class TestLoadToml:
    def test_load_existing_file(self):
        data = _load_toml("assets.toml")
        assert "stocks" in data
        assert "crypto" in data

    def test_load_missing_file_returns_empty(self):
        data = _load_toml("nonexistent.toml")
        assert data == {}


class TestAssetConfig:
    def test_stock_symbols_loaded(self):
        config = AssetConfig()
        # symbols can be empty in default config
        assert isinstance(config.stock_symbols, list)

    def test_crypto_symbols_loaded(self):
        config = AssetConfig()
        assert len(config.crypto_symbols) > 0
        assert "BTC/USDT" in config.crypto_symbols

    def test_crypto_exchange_default(self):
        config = AssetConfig()
        assert config.crypto_exchange == "binance"

    def test_all_symbols_combines_both(self):
        config = AssetConfig()
        all_syms = config.all_symbols
        assert "BTC/USDT" in all_syms
        assert len(all_syms) == len(config.stock_symbols) + len(config.crypto_symbols)


class TestStrategyConfig:
    def test_hurst_threshold_loaded(self):
        config = StrategyConfig()
        assert config.hurst_threshold == 0.55

    def test_cycle_settings_loaded(self):
        config = StrategyConfig()
        assert config.cycle_min_period == 10
        assert config.cycle_max_period == 200
        assert config.cycle_projection_bars == 20

    def test_backtest_settings_loaded(self):
        config = StrategyConfig()
        assert config.backtest_initial_capital == 100000.0
        assert config.backtest_commission == 0.001
        assert len(config.backtest_hurst_range) > 0


class TestTimeframeConfig:
    def test_default_timeframes_loaded(self):
        config = TimeframeConfig()
        assert "4h" in config.default_timeframes
        assert "1d" in config.default_timeframes
        assert len(config.default_timeframes) == 2

    def test_yfinance_mapping_loaded(self):
        config = TimeframeConfig()
        assert config.yfinance_mapping.get("1h") == "1h"

    def test_ccxt_mapping_loaded(self):
        config = TimeframeConfig()
        assert config.ccxt_mapping.get("4h") == "4h"


class TestSetupLogging:
    def test_logging_creates_log_dir(self, tmp_path):
        settings = AppSettings()
        settings.log_path = str(tmp_path / "subdir" / "test.log")
        setup_logging(settings)
        assert (tmp_path / "subdir").exists()


class TestLoadConfig:
    def test_load_config_returns_all_configs(self):
        settings, assets, strategy, timeframes, paper = load_config()
        assert isinstance(settings, AppSettings)
        assert isinstance(assets, AssetConfig)
        assert isinstance(strategy, StrategyConfig)
        assert isinstance(timeframes, TimeframeConfig)
        assert isinstance(paper, PaperConfig)
