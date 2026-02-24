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

Rabbit-Quant supports both local DuckDB and PostgreSQL. **PostgreSQL is required for concurrent workflows** (running scheduler and dashboard at the same time).

| Variable | Default | Description |
|----------|---------|-------------|
| `DUCKDB_PATH` | `data/rabbit.duckdb` | Local database file (fallback) |
| `DATABASE_HOST` | `localhost` | Postgres Host |
| `DATABASE_PORT` | `5432` | Postgres Port |
| `DATABASE_NAME` | `rabbit_quant` | Postgres DB Name |
| `DATABASE_USER` | - | Postgres Username |
| `DATABASE_PASSWORD` | - | Postgres Password |
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

## Workflow Guide

### Path A: Research & Strategy Optimization (One-time)

Use this workflow to find the best performing assets and fine-tune your strategy parameters.

**1. Optimize Entire Market:**
Fetch fresh data and find the best parameters for every asset in your watchlist.
```bash
uv run python main.py backtest-all --type crypto --sweep --fetch
```

**2. Analyze Results:**
Check the leaderboard in the console and open `data/backtest/summary_bulk_crypto.csv` to see which symbols/timeframes have the highest Sharpe Ratio.

**3. Deep Dive:**
Run a detailed sweep for a single promising asset:
```bash
uv run python main.py backtest -s SOL/USDT -t 1h --sweep
```
*(Optionally apply recommendations to `config/strategy.toml` when prompted).*

### Path B: Continuous Live Monitoring (Server Mode)

Use this workflow to keep your data fresh, calculate signals in the background, and receive real-time alerts. **Requires PostgreSQL.**

**1. Start the Writer Service (Terminal 1):**
This service runs continuously, fetching data and scanning for signals every X minutes. It also sends Telegram alerts if configured.
```bash
uv run python main.py run-scheduler --interval 5
```

**2. Launch the Dashboard (Terminal 2):**
Monitor the market visually. The dashboard will automatically reflect updates from the Writer Service.
```bash
uv run python main.py dashboard
```

---

## Running Tests

```bash
# Run all tests
uv run pytest

# With coverage report
uv run pytest --cov=src --cov-report=term-missing

# Run specific module tests
uv run pytest tests/test_cycles.py -v
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
- `0.5-0.6`: Many signals, lower confidence
- `0.6-0.7`: Balanced — recommended starting point
- `0.7-0.9`: Fewer signals, only strong trends

**Cycle Phase Centers (radians)**
- `phase_long_center` (~4.712 = 3π/2): Where long entries trigger (cycle trough)
- `phase_short_center` (~1.571 = π/2): Where short entries trigger (cycle peak)

### Optimization Workflow

**Step 1: Fetch fresh data**
```bash
uv run python main.py fetch
```

**Step 2: Run sweep on your target asset**
```bash
uv run python main.py backtest -s SOL/USDT -t 1h --sweep
```

**Step 3: Analyze results**
Open `data/backtest/sweep_SOLUSDT_1h.csv` to see all 225 combinations.

**Step 4: Apply recommended parameters**
Update `config/strategy.toml` with the top-ranked values.

---

## Project Structure

```
rabbit-quant/
├── main.py                          # CLI: fetch, backtest, dashboard, run-scheduler
├── config/
│   ├── assets.toml                  # Stock & crypto watchlists
│   ├── strategy.toml                # Hurst/cycle/backtest parameters
│   └── timeframes.toml              # Timeframe definitions
├── src/
│   ├── config.py                    # Pydantic Settings + TOML loading
│   ├── data_loader.py               # DuckDB/Postgres schema & operations
│   ├── services/
│   │   ├── scheduler.py             # Background ingestion service
│   │   └── notifier.py              # Telegram notification service
│   ├── fetchers/                    # market data APIs
│   ├── signals/                     # Math Core (FFT, Hurst)
│   ├── backtest/                    # VectorBT Engine
│   └── dashboard/                   # Streamlit UI
├── tests/                           # pytest suite
└── data/                            # Local DB & reports
```

---

## Production Runbook

To run Rabbit-Quant as a full trading workstation:

**1. Prerequisites**
- PostgreSQL database running
- `.env` file configured with DB credentials and Telegram tokens

**2. Start the Backend (Writer Service)**
Open Terminal 1:
```bash
uv run python main.py run-scheduler --interval 5
```
*   Fetches data every 5 minutes
*   Scans for signals
*   Sends Telegram alerts
*   Logs to `logs/trading_signals.log`

**3. Start the Frontend (Dashboard)**
Open Terminal 2:
```bash
uv run python main.py dashboard
```
*   Visualizes market data
*   Shows Confluence Heatmap
*   Auto-refreshes every 60s without locking the database
