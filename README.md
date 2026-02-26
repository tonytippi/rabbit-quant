# Quant-Rabbit Local Core

**Version:** 2.1 (Live Paper Trading)  
**Language:** Python 3.10+  
**Target Hardware:** AMD Ryzen 7 7735HS (8C/16T), 64GB DDR5 RAM, NVMe SSD

---

## Overview

**Quant-Rabbit Local Core** is a high-performance, privacy-focused Quantitative Trading Workstation designed to run entirely on consumer hardware. It replicates institutional-grade analytics—specifically **Market Cycles (Spectral Analysis)** and **Fractal Geometry (Hurst Exponent)**—to identify high-probability turning points in financial markets.

### Key Features

- ✅ **100% Local Execution** - No cloud servers, no SaaS fees ($0.00 operational cost)
- 📊 **Advanced Analytics** - FFT-based Cycle Detection and Hurst Exponent calculations
- 💰 **Paper Trading Mode** - Simulate live trading with a virtual $1,000 balance
- 🚀 **High Performance** - Process 10,000 candles in under 0.05 seconds
- 📈 **Multi-Asset Support** - Fetch and analyze 50+ assets simultaneously
- 💾 **DuckDB Storage** - Fast local data storage and retrieval
- 🎯 **Real-time Simulation** - Account for actual exchange fees (Binance standard: 0.1%)

---

## Problem Statement

Retail traders struggle to validate strategies in real-time. Backtesting is useful, but it doesn't account for live market pressure or the cumulative impact of trading fees. Quant-Rabbit provides a safe "sandbox" to test algorithms on live data before deploying real capital.

---

## Target Users

- **The Algo-Researcher:** Backtest complex hypotheses on years of historical data
- **The Forward Tester:** Watch a bot trade virtual money in real-time to verify strategies against live spreads and fees

---

## Success Metrics

| Metric | Target |
| :--- | :--- |
| **Signal Accuracy** | >65% win rate over 100-trade backtest |
| **Simulation Accuracy** | Paper trading PnL within 0.5% of theoretical |
| **Data Throughput** | Fetch/store 50+ assets in under 60 seconds |
| **Compute Speed** | Calculate Hurst for 10,000 candles in <0.05s |
| **Operational Cost** | $0.00 (no cloud, no subscriptions) |

---

## Documentation

### Core Documents
- **Product Requirement Document (PRD):** [docs/prd.md](docs/prd.md)
- **Getting Started Guide:** [docs/getting-started.md](docs/getting-started.md)
- **Development Roadmap:** [docs/development-roadmap.md](docs/development-roadmap.md)
- **Project Overview (PDR):** [docs/project-overview-pdr.md](docs/project-overview-pdr.md)

### Planning Artifacts
- **Architecture:** [_bmad-output/planning-artifacts/architecture.md](_bmad-output/planning-artifacts/architecture.md)
- **Epics:** [_bmad-output/planning-artifacts/epics.md](_bmad-output/planning-artifacts/epics.md)
- **User Stories:** [_bmad-output/planning-artifacts/stories/](_bmad-output/planning-artifacts/stories/)

---

## Architecture

### Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.10+ | Core application logic |
| **Database** | DuckDB | Fast local OHLCV storage |
| **Math Engine** | SciPy / Numba | Signal processing & optimization |
| **Paper Trading** | Custom Python Class | Wallet & fee simulation |
| **Frontend** | Streamlit | Interactive dashboard |
| **Data Sources** | yfinance / ccxt | Market data ingestion |

### Directory Structure

```text
rabbit-quant/
├── config/
│   ├── assets.toml             # Asset watchlist (Crypto/Stocks)
│   ├── strategy.toml           # Hurst/Cycle/Risk parameters
│   └── timeframes.toml         # Timeframe mappings
├── data/
│   ├── rabbit.duckdb           # Historical OHLCV data
│   └── backtest/               # Backtest reports (CSV)
├── src/
│   ├── config.py               # Config loader (Pydantic)
│   ├── data_loader.py          # Database operations
│   ├── signals/                # Math Core (FFT, Hurst)
│   ├── backtest/               # VectorBT Engine
│   ├── dashboard/              # Streamlit UI
│   └── services/               # Background scheduler
├── main.py                     # CLI Entry point
└── pyproject.toml              # Dependencies (uv)
```

---

## Installation

### Prerequisites

- Python 3.10+ (tested on 3.12)
- [uv](https://docs.astral.sh/uv/) package manager
- 8GB+ RAM (64GB recommended for large datasets)
- NVMe SSD for optimal database performance

### Setup

```bash
# Clone the repository
git clone <repository-url> && cd rabbit-quant

# Install dependencies
uv sync

# Copy environment config
cp .env.example .env
```

---

## Usage

Rabbit-Quant is operated via the `main.py` CLI. Ensure you have configured your environment variables in `.env` and assets in `config/assets.toml`.

### 1. Research & Strategy Optimization (One-time)

Fetch fresh data and find the best parameters for every asset in your watchlist:

```bash
uv run python main.py backtest-all --type crypto --sweep --fetch
```

Run a detailed parameter sweep for a single promising asset:

```bash
uv run python main.py backtest -s SOL/USDT -t 1h --sweep
```

### 2. Continuous Live Monitoring (Server Mode)

Use this workflow to keep your data fresh, calculate signals in the background, and view the dashboard. **Requires PostgreSQL setup for concurrent access.**

**Start the Writer Service (Terminal 1):**

```bash
uv run python main.py run-scheduler --interval 5
```

**Launch the Dashboard (Terminal 2):**

```bash
uv run python main.py dashboard
```

---

## Core Modules

### 🔹 Epic 1: Data Ingestion ("The Lake")
- Async fetcher for multiple data sources
- DuckDB storage for efficient querying
- Live updater (1-minute intervals)

### 🔹 Epic 2: Quantitative Engine ("The Brain")
- **FFT Cycle Detector**: Low-pass filter for dominant cycles
- **Hurst Calculator**: Numba-optimized fractal analysis
- **Phase Projection**: Sine wave overlay for future predictions

### 🔹 Epic 3: Paper Trading Engine ("The Simulator")
- **Virtual Wallet**: Tracks USD balance and asset holdings
- **Fee Logic**: Applies 0.1% fee per transaction
- **Order Manager**: Executes buy/sell at close prices
- **Trade Journal**: Logs all transactions for audit

### 🔹 Epic 4: Dashboard ("The Cockpit")
- Streamlit-based interactive UI
- Plotly charts with cycle overlays
- Real-time PnL widget showing account value changes

---

## Key Features in Detail

### Market Cycle Analysis (Spectral Analysis)
Uses Fast Fourier Transform (FFT) to identify dominant market cycles and predict potential turning points based on historical price patterns.

### Fractal Geometry (Hurst Exponent)
Calculates the Hurst Exponent to measure market "memory" and trend persistence:
- **H < 0.5**: Mean-reverting market
- **H = 0.5**: Random walk
- **H > 0.5**: Trending market

### Paper Trading Features
- Virtual account initialization (default: $1,000)
- Real-time fee calculation (0.1% per trade)
- Unrealized PnL tracking (open positions)
- Realized PnL tracking (closed trades)
- Stop Loss and Take Profit logic
- Trade validation (prevents over-trading)

---

## Roadmap

### ✅ MVP (Current Phase)
- Data Pipeline
- Math Core (FFT/Hurst)
- Paper Trading Engine
- Console-based signals

### 🔄 Growth Phase (In Progress)
- Streamlit Dashboard
- VectorBT Backtesting
- Heatmap optimization
- Interactive charts

### 🔮 Vision (Future)
- Live API trading (Binance/Alpaca)
- Reinforcement Learning agent
- Multi-strategy portfolio management

---

## Performance Benchmarks

- **Compute Speed**: <0.05s for 10,000 candles
- **Data Throughput**: 50+ assets in <60s
- **Memory Efficiency**: Optimized for 64GB RAM
- **Storage**: DuckDB provides 10x faster queries than SQLite

---

## Configuration

Settings are managed via TOML files in `config/` and environment variables in `.env`.

### 1. Strategy Settings (`config/strategy.toml`)

```toml
[hurst]
threshold = 0.55          # Min Hurst for directional signals

[filters]
macro_filter_type = "both" # "hurst", "chop", or "both"
htf_threshold = 50.0       # Daily Chop Threshold
ltf_threshold = 55         # LTF Consolidation Threshold

[risk]
risk_per_trade = 0.02      # 2% Risk per trade
max_concurrent_trades = 2  # Max open positions
```

### 2. Environment Variables (`.env`)

Used for database credentials, logging levels, and notifications:

```bash
# Database (DuckDB or Postgres)
DUCKDB_PATH="data/rabbit.duckdb"

# Notifications
TELEGRAM_BOT_TOKEN="your_token"
TELEGRAM_CHAT_ID="your_chat_id"
```

---

## Contributing

This is a personal research project. If you'd like to contribute or have suggestions, please open an issue or submit a pull request.

---

## License

[Add your license here]

---

## Disclaimer

⚠️ **This software is for educational and research purposes only.** Trading financial instruments involves substantial risk of loss. Past performance does not guarantee future results. Always test strategies thoroughly before risking real capital.

---

## Contact

For questions or support, please open an issue on the repository.

---

**Built with ❤️ for the quantitative trading community**
