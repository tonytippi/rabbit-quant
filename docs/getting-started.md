# Getting Started

## Prerequisites

- Python 3.10+ (tested on 3.12)
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
# Clone the repository
git clone <repo-url> && cd rabbit-quant

# Install dependencies
uv sync

# Copy environment config
cp .env.example .env
```

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DUCKDB_PATH` | `data/rabbit.duckdb` | Database file location |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_PATH` | `logs/rabbit.log` | Log file path |
| `YFINANCE_PROXY` | _(empty)_ | HTTP proxy for yfinance requests |
| `TELEGRAM_BOT_TOKEN` | _(empty)_ | Token from @BotFather for trade alerts |
| `TELEGRAM_CHAT_ID` | _(empty)_ | Chat ID to receive alerts |

### Asset Watchlist (`config/assets.toml`)

Edit to add/remove symbols:

```toml
[stocks]
symbols = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]

[crypto]
symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
exchange = "binance"
```

### Strategy Parameters (`config/strategy.toml`)

```toml
[hurst]
threshold = 0.6          # Min Hurst for directional signals (0.5-0.9)
min_data_points = 256    # Min bars needed for cycle detection

[cycle]
min_period = 10          # Shortest cycle to detect (bars)
max_period = 200         # Longest cycle to detect (bars)
projection_bars = 20     # Forward projection length
lowpass_cutoff = 0.1     # Butterworth filter cutoff (0.01-0.99)

[backtest]
initial_capital = 100000.0
commission = 0.001       # 0.1% per trade
output_dir = "data/backtest"
# Parameter sweep ranges (used with --sweep flag)
hurst_range = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
phase_long_range = [4.0, 4.4, 4.712, 5.0, 5.5]
phase_short_range = [1.0, 1.3, 1.571, 1.8, 2.1]
```

### Timeframe Mappings (`config/timeframes.toml`)

Supported: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`. Note: yfinance does not support 4h natively — the system fetches 1h data and resamples automatically.

---

## Quick Start

### 1. Fetch Market Data

```bash
uv run python main.py fetch
```

Downloads OHLCV data for all configured symbols across all timeframes. Data is stored in DuckDB with upsert semantics (safe to re-run).

**Output example:**
```
Fetch Summary: 18/20 succeeded, 45000 rows upserted in 12.3s
Failed: 2 symbol/timeframe combinations
```

### 2. Run a Single Backtest

```bash
uv run python main.py backtest -s AAPL -t 1d
```

Runs the cycle+Hurst strategy on AAPL daily data using parameters from `config/strategy.toml`.

**Output example:**
```
Backtest Results for AAPL/1d:
  Total Return: 23.45%
  Sharpe Ratio: 1.2340
  Max Drawdown: -8.76%
  Win Rate:     62.5%
  Total Trades: 24
```

Trade log exported to `data/backtest/trades_AAPL_1d.csv`.

### 3. Run Parameter Sweep

```bash
uv run python main.py backtest -s AAPL -t 1d --sweep
```

Tests all combinations from `config/strategy.toml` sweep ranges and ranks by Sharpe Ratio.

**Output example:**
```
Parameter Sweep Results (225 combinations):
Top 3 by Sharpe Ratio:
  #1: Hurst≥0.65, PhaseLong=4.712, PhaseShort=1.571 | Sharpe=1.5432 ← RECOMMENDED
  #2: Hurst≥0.60, PhaseLong=4.400, PhaseShort=1.571 | Sharpe=1.3210
  #3: Hurst≥0.70, PhaseLong=5.000, PhaseShort=1.300 | Sharpe=1.1890
```

Full results saved to `data/backtest/sweep_AAPL_1d.csv`.

### 4. Bulk Backtesting & Market Scanning

```bash
uv run python main.py backtest-all --type crypto --sweep --fetch
```

Optimizes the strategy for **every** symbol in your watchlist across **all** timeframes in a single run. The `--fetch` flag ensures all data is fresh before starting.

**Output example:**
```
Bulk run complete in 86.1s. Processed 48 combinations.

=== LEADERBOARD (Top 10) ===
    symbol timeframe  sharpe_ratio  total_return  max_drawdown  best_hurst_threshold
 AVAX/USDT        1d      1.970207   4204.827466     49.719854                   0.5
  SOL/USDT        1h      1.779964    104.330773      9.085976                   0.5
 ...
```

Consolidated results are saved to `data/backtest/summary_bulk_crypto.csv`.

### 5. Launch Dashboard

```bash
uv run python main.py dashboard
```

Opens browser at `http://localhost:8501` with:
- **Scanner table** — all assets sorted by Hurst exponent
- **Candlestick chart** — interactive with zoom/pan/crosshair
- **Sine wave overlay** — historical fit + forward projection (dashed)
- **Signal markers** — green triangles (long) / red triangles (short)
- **Auto-refresh** — every 60 seconds

---

## Running Tests

```bash
# Run all 140 tests
uv run pytest

# With coverage report
uv run pytest --cov=src --cov-report=term-missing

# Run specific module tests
uv run pytest tests/test_cycles.py -v
uv run pytest tests/test_vbt_runner.py -v

# Run only fast tests (exclude slow backtest sweep)
uv run pytest -k "not sweep_with_defaults"
```

## Linting

```bash
# Check
uv run ruff check src/ tests/

# Auto-fix
uv run ruff check --fix src/ tests/
```

---

## Parameter Optimization Guide

### Understanding the Parameters

**Hurst Threshold (`hurst.threshold`)**
- Controls signal sensitivity. Higher = fewer but more confident signals.
- `0.5-0.6`: Many signals, lower confidence (random-walk-like markets still trigger)
- `0.6-0.7`: Balanced — recommended starting point
- `0.7-0.9`: Fewer signals, only strong trends

**Cycle Phase Centers (radians)**
- `phase_long_center` (~4.712 = 3π/2): Where long entries trigger (cycle trough)
- `phase_short_center` (~1.571 = π/2): Where short entries trigger (cycle peak)
- Adjusting these shifts the entry timing relative to the cycle

**Low-pass Cutoff (`cycle.lowpass_cutoff`)**
- Controls noise filtering before cycle detection
- Lower = more smoothing (0.05: heavy smoothing, 0.2: light smoothing)
- Default 0.1 is good for most cases

### Optimization Workflow

**Step 1: Fetch fresh data**
```bash
uv run python main.py fetch
```

**Step 2: Run sweep on your target asset**
```bash
uv run python main.py backtest -s AAPL -t 1d --sweep
```

**Step 3: Analyze results**

Open `data/backtest/sweep_AAPL_1d.csv` to see all 225 combinations with:
- `hurst_threshold`, `phase_long`, `phase_short`
- `total_return`, `sharpe_ratio`, `max_drawdown`, `win_rate`, `total_trades`

**Step 4: Apply recommended parameters**

Update `config/strategy.toml` with the top-ranked values:
```toml
[hurst]
threshold = 0.65  # from sweep recommendation

[backtest]
# Narrow ranges around optimal for fine-tuning
hurst_range = [0.60, 0.62, 0.65, 0.67, 0.70]
phase_long_range = [4.5, 4.6, 4.712, 4.8, 4.9]
phase_short_range = [1.4, 1.5, 1.571, 1.6, 1.7]
```

**Step 5: Fine-tune with narrower sweep**
```bash
uv run python main.py backtest -s AAPL -t 1d --sweep
```

**Step 6: Verify on different timeframes**
```bash
uv run python main.py backtest -s AAPL -t 1h --sweep
uv run python main.py backtest -s AAPL -t 4h --sweep
```

### Tips

- **Avoid overfitting**: If optimal parameters only work on one asset/timeframe, they're likely overfit. Test across multiple assets.
- **Sharpe > 1.0**: Generally considered good risk-adjusted performance.
- **Max Drawdown**: Keep below 20% for sustainable strategies.
- **Total Trades**: Too few (<10) means insufficient statistical significance.
- **Walk-forward**: Split data into in-sample (optimize) and out-of-sample (validate) periods manually by adjusting the fetch date range.

### 6. Server Deployment (Writer Service)

For server deployments where multiple components (Dashboard, Backtester) need concurrent access, use the **Writer Service** to avoid DuckDB locking conflicts.

**Features:**
*   **Automatic Data Ingestion:** Fetches new market data every X minutes.
*   **Headless Signal Scanning:** Calculates signals immediately after fetching.
*   **Telegram Alerts:** Sends instant notifications for BUY/SELL signals if configured in `.env`.

**Step 1: Start the Ingestion Service (The Writer)**
This process owns the write lock and updates data periodically.
```bash
uv run python main.py run-scheduler --interval 5
```

**Step 2: Start the Dashboard (The Reader)**
The dashboard connects in read-only mode and will see updates from the Writer Service.
```bash
uv run python main.py dashboard
```

---

## Project Structure

```
rabbit-quant/
├── main.py                          # CLI: fetch, backtest, dashboard
├── config/
│   ├── assets.toml                  # Stock & crypto watchlists
│   ├── strategy.toml                # Hurst/cycle/backtest parameters
│   └── timeframes.toml              # Timeframe mappings
├── src/
│   ├── config.py                    # Pydantic Settings + TOML loading
│   ├── data_loader.py               # DuckDB schema, upsert, query
│   ├── fetchers/
│   │   ├── stock_fetcher.py         # yfinance OHLCV fetching
│   │   ├── crypto_fetcher.py        # ccxt async crypto fetching
│   │   └── orchestrator.py          # Concurrent ingestion coordinator
│   ├── signals/
│   │   ├── cycles.py                # FFT cycle detection + low-pass filter
│   │   ├── fractals.py              # Numba Hurst R/S exponent
│   │   └── filters.py               # Combined signal generation
│   ├── backtest/
│   │   ├── vbt_runner.py            # VectorBT engine + parameter sweep
│   │   └── analyzer.py              # Metrics, CSV export, auto-discovery
│   └── dashboard/
│       ├── app.py                   # Streamlit scanner + routing
│       └── charts.py                # Plotly candlestick + overlays
├── tests/                           # 140 tests (13 files)
├── data/                            # DuckDB database + backtest outputs
└── logs/                            # Loguru rotating log files
```
