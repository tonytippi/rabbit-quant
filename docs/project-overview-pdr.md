# Rabbit-Quant — Project Overview

High-performance local quantitative trading workstation. Detects dominant market cycles via FFT, measures trend persistence via Hurst Exponent, generates trading signals, backtests strategies with parameter optimization, and visualizes everything on an interactive dashboard.

## Architecture

```
main.py (CLI)
    ├── fetch    → fetchers/ → data_loader → DuckDB
    ├── backtest → signals/ + backtest/
    └── dashboard → Streamlit + Plotly
```

**Module boundaries:** asyncio for I/O (fetchers), Numba for math (signals), ProcessPoolExecutor for batch compute (backtest), Streamlit event loop (dashboard).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12, uv package manager |
| Database | DuckDB (embedded OLAP) |
| Data Sources | yfinance (stocks), ccxt (crypto) |
| Signal Math | NumPy FFT, SciPy Butterworth filter, Numba @njit |
| Backtesting | VectorBT |
| Dashboard | Streamlit + Plotly |
| Config | Pydantic Settings (.env) + TOML files |
| Logging | Loguru with file rotation |
| Testing | pytest (140 tests) |
| Linting | ruff |

## Project Stats

- **Source code:** 1,888 lines across 12 modules
- **Test code:** 1,377 lines across 13 test files
- **Test count:** 140 (all passing)
- **Dependencies:** 15 runtime + 5 dev

## Epics

| # | Epic | Stories | Status |
|---|------|---------|--------|
| 1 | Data Acquisition & Storage | 1.1-1.5 | Complete |
| 2 | Quantitative Signal Generation | 2.1-2.5 | Complete |
| 3 | Strategy Backtesting & Optimization | 3.1-3.5 | Complete |
| 4 | Interactive Trading Dashboard | 4.1-4.4 | Complete |
