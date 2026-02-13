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
quant_rabbit/
├── data/
│   ├── market_data.duckdb      # Historical OHLCV data
│   └── paper_trades.csv        # Virtual trade log
├── src/
│   ├── config.py               # System configuration
│   ├── data_loader.py          # Async data fetcher
│   ├── signals/
│   │   ├── cycles.py           # FFT Cycle Detector
│   │   └── fractals.py         # Hurst Exponent Calculator
│   ├── paper/
│   │   ├── wallet.py           # Virtual account manager
│   │   └── broker.py           # Order execution & fees
│   ├── dashboard/
│   │   └── app.py              # Streamlit UI
├── main.py                     # Application entry point
└── requirements.txt            # Python dependencies
```

---

## Installation

### Prerequisites

- Python 3.10 or higher
- 8GB+ RAM (64GB recommended for large datasets)
- NVMe SSD for optimal database performance

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd rabbit-quant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

### 1. Backtest Mode (Historical Analysis)

```bash
# Fetch 5 years of historical data
python data_loader.py --symbol BTC-USD --years 5

# Run backtest with custom configuration
python main.py --backtest --config backtest_config.json

# View results in dashboard
streamlit run src/dashboard/app.py
```

### 2. Paper Trading Mode (Live Simulation)

```bash
# Configure paper trading in config.py
# Set: PAPER_TRADE_MODE = True
# Set: INITIAL_BALANCE = 1000

# Launch live paper trading
python main.py --live

# Monitor real-time PnL in dashboard
streamlit run src/dashboard/app.py
```

### Paper Trading Workflow

1. System fetches latest 1-minute candle from Binance
2. Math engine calculates Cycle Bottom + Hurst Exponent
3. Signal detected (e.g., Hurst > 0.75)
4. Virtual BUY executed at current close price
5. 0.1% fee deducted from transaction
6. Balance and holdings updated in wallet
7. Trade logged to `data/paper_trades.csv`
8. Dashboard displays real-time portfolio value

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

Key settings in `src/config.py`:

```python
# Paper Trading
PAPER_TRADE_MODE = True
INITIAL_BALANCE = 1000
TRADING_FEE = 0.001  # 0.1%

# Signal Thresholds
HURST_THRESHOLD = 0.6
CYCLE_CONFIDENCE = 0.75

# Data Settings
UPDATE_INTERVAL = 60  # seconds
MAX_ASSETS = 50
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
