# PRODUCT REQUIREMENT DOCUMENT (PRD)
**Project Name:** Quant-Rabbit Local Core
**Version:** 2.1 (Live Paper Trading)
**Date:** 2026-02-13
**Target Hardware:** AMD Ryzen 7 7735HS (8C/16T), 64GB DDR5 RAM, NVMe SSD
**Language:** Python 3.10+

---

## 1. Executive Summary
**Quant-Rabbit Local Core** is a high-performance, privacy-focused Quantitative Trading Workstation designed to run entirely on consumer hardware. It replicates institutional-grade analytics—specifically **Market Cycles (Spectral Analysis)** and **Fractal Geometry (Hurst Exponent)**—to identify high-probability turning points.

**Update v2.1:** The system now includes a **"Paper Trading" mode** to simulate live execution with a virtual \$1,000 balance, accounting for real-world exchange fees (Binance) without risking actual capital.

### 1.1 Problem Statement
Retail traders struggle to validate strategies in real-time. Backtesting is useful, but it doesn't account for live market pressure or the cumulative impact of trading fees. Users need a safe "sandbox" to test their algorithms on live data before deploying real money.

### 1.2 Target Personas
* **The Algo-Researcher:** Needs to backtest complex hypotheses on years of data.
* **The Forward Tester (NEW):** Needs to watch a bot trade \$1,000 of "fake money" in real-time to verify if the backtest results hold up against live spreads and fees.

---

## 2. Success Criteria (SMART Goals)
The project is considered successful if it meets the following metrics:

| Metric | Target |
| :--- | :--- |
| **Signal Accuracy** | Achieve a theoretical trade win rate of **>65%** over a 100-trade backtest sample. |
| **Simulation Accuracy** | Paper trading PnL must match "real" theoretical PnL within **0.5%** error margin (accounting for fees). |
| **Data Throughput** | Fetch, clean, and store OHLCV updates for **50+ assets** in under **60 seconds**. |
| **Compute Speed** | Calculate Hurst Exponent for **10,000 candles** in under **0.05 seconds**. |
| **Operational Cost** | **$0.00**. No cloud servers, no SaaS fees. |

---

## 3. Product Scope (Phasing)

### 3.1 MVP (Minimum Viable Product)
* **Focus:** Data Pipeline, Math Core, & Paper Trading.
* **Features:** Async data fetching, DuckDB storage, FFT/Hurst Engine, **Virtual Wallet ($1k)**, Fee Calculator.
* **Output:** Console-based signal generation + "Virtual Trade" log file.

### 3.2 Growth Phase
* **Focus:** Visuals & Optimization.
* **Features:** Streamlit Dashboard, VectorBT Backtesting, Heatmap optimization.
* **Output:** Interactive charts with Cycle overlays and Real-time PnL graph.

### 3.3 Vision (Future State)
* **Focus:** Real Execution.
* **Features:** Live API trading (Binance/Alpaca), RL Agent optimization.

---

## 4. User Journeys

### Persona 1: The Researcher (Backtesting)
> **Goal:** Validate if "Cycle Bottoms" are profitable over the last 5 years.
1.  **Ingest:** Runs `python data_loader.py --symbol BTC-USD --years 5`.
2.  **Simulate:** Configures `backtest_config.json` (Hurst > 0.6).
3.  **Analyze:** Reviews Heatmap to find the best timeframe (e.g., 4H).

### Persona 2: The Forward Tester (Live Paper Trading) - NEW
> **Goal:** Watch the bot trade a $1,000 virtual account on live Binance data.
1.  **Configure:** User sets `PAPER_TRADE_MODE = True` and `INITIAL_BALANCE = 1000` in `config.py`.
2.  **Launch:** Runs `python main.py --live`.
3.  **Monitor:** The system fetches the latest 1-minute candle from Binance.
4.  **Signal:** Math engine detects a Cycle Bottom + Hurst 0.75.
5.  **Execute:** System records a "VIRTUAL BUY" at \$95,000.
    * *Logic:* Deducts 0.1% fee (\$1.00). Balance is now \$0 USD, Holding 0.0105 BTC.
6.  **Update:** Dashboard updates "Current Portfolio Value" in real-time as price moves.

---

## 5. System Modules (Epics)

### Epic 1: Data Ingestion ("The Lake")
* **Story 1.1:** Async fetcher for `yfinance`/`ccxt`.
* **Story 1.2:** DuckDB storage.
* **Story 1.3:** Live Updater (1-minute intervals).

### Epic 2: Quantitative Engine ("The Brain")
* **Story 2.1:** FFT Cycle Detector (Low-pass filter).
* **Story 2.2:** Numba-optimized Hurst Calculator.
* **Story 2.3:** Phase Projection (Sine Wave overlay).

### Epic 3: Paper Trading Engine ("The Simulator") - NEW
**Objective:** Simulate a real exchange environment.
* **Story 3.1 (Virtual Wallet):** Create a `Wallet` class that tracks `USD_Balance` and `Asset_Holdings`. It must initialize with \$1,000.
* **Story 3.2 (Fee Logic):** Implement a fee deductor. Every trade (Buy/Sell) must subtract **0.1%** (Binance standard fee) from the transaction value.
* **Story 3.3 (Order Manager):** Implement `buy()` and `sell()` functions that execute at the *Close* price of the latest candle.
* **Story 3.4 (Trade Journal):** Log every transaction to `data/paper_trades.csv` (Time, Type, Price, Amount, Fee, Net Balance).

### Epic 4: Dashboard ("The Cockpit")
* **Story 4.1:** Streamlit Layout.
* **Story 4.2:** Plotly Charts with Cycle Overlay.
* **Story 4.3:** **Live PnL Widget:** A real-time counter showing "Account Value: \$1,025 (+2.5%)".

---

## 6. Functional Requirements (FR)

### Data & Math
* **FR-01:** System must fetch OHLCV data for 50+ assets asynchronously.
* **FR-02:** System must calculate Dominant Cycle & Hurst Exponent (<0.05s).
* **FR-03:** System must project cycle phase 20 bars into the future.

### Paper Trading (Virtual Execution)
* **FR-19:** System must initialize a virtual account with a configurable balance (Default: \$1,000).
* **FR-20:** System must apply a **0.1% trading fee** to every buy and sell order.
* **FR-21:** System must track "Unrealized PnL" (open positions) and "Realized PnL" (closed trades).
* **FR-22:** System must prevent "over-trading" (cannot buy if USD balance < min_order_size).
* **FR-23:** System must log all virtual trades to a CSV file for audit.
* **FR-24:** System must support "Stop Loss" and "Take Profit" logic in paper mode (e.g., Sell if price drops 2%).

---

## 7. Technical Architecture

### 7.1 Tech Stack
| Component | Technology | Justification |
| :--- | :--- | :--- |
| **Backend** | Python 3.10+ | Standard. |
| **Database** | DuckDB | Fast local storage. |
| **Math** | SciPy / Numba | Signal processing & optimization. |
| **Simulation** | **Custom Python Class** | Simple state-machine for wallet/fees. |
| **Frontend** | Streamlit | UI. |

### 7.2 Directory Structure
```text
quant_rabbit/
├── data/
│   ├── market_data.duckdb
│   └── paper_trades.csv    # NEW: Trade Log
├── src/
│   ├── config.py           # Settings (INITIAL_BALANCE = 1000, FEE = 0.001)
│   ├── data_loader.py
│   ├── signals/
│   │   ├── cycles.py
│   │   └── fractals.py
│   ├── paper/              # NEW MODULE
│   │   ├── wallet.py       # Manages Balance & Holdings
│   │   └── broker.py       # Executes virtual orders & Calcs Fees
│   ├── dashboard/
│   │   └── app.py
├── main.py
└── requirements.txt