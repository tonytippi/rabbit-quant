# PRODUCT REQUIREMENT DOCUMENT (PRD)
**Project Name:** Quant-Rabbit Local Core
**Version:** 2.0 (BMAD Compatible)
**Date:** 2026-02-12
**Target Hardware:** AMD Ryzen 7 7735HS (8C/16T), 64GB DDR5 RAM, NVMe SSD
**Language:** Python 3.10+

---

## 1. Executive Summary
**Quant-Rabbit Local Core** is a high-performance, privacy-focused Quantitative Trading Workstation designed to run entirely on consumer hardware. It replicates institutional-grade analytics—specifically **Market Cycles (Spectral Analysis)** and **Fractal Geometry (Hurst Exponent)**—to identify high-probability turning points in financial markets.

### 1.1 Problem Statement
Retail traders rely on lagging indicators (RSI, MACD) and expensive SaaS platforms (TradingView, Bloomberg) that obscure the underlying math. They lack the ability to process raw market data non-linearly or perform heavy computational analysis without incurring significant cloud costs.

### 1.2 Target Personas
* **The Algo-Researcher:** Needs to backtest complex hypotheses on years of data without waiting hours for results.
* **The Discretionary Quant:** Needs real-time, mathematically grounded signals to support manual execution, not black-box advice.

### 1.3 Competitive Differentiator
Unlike TradingView (visual only) or QuantConnect (cloud-dependent), Quant-Rabbit offers **Zero-Latency Local Compute**. It leverages the user's powerful local hardware (Ryzen 7, 64GB RAM) to run heavy math (FFT/Fractals) on 50+ assets simultaneously with no monthly fees and total data privacy.

---

## 2. Success Criteria (SMART Goals)
The project is considered successful if it meets the following metrics:

| Metric | Target |
| :--- | :--- |
| **Signal Accuracy** | Achieve a theoretical trade win rate of **>65%** over a 100-trade backtest sample on BTC/ETH. |
| **Data Throughput** | Fetch, clean, and store OHLCV updates for **50+ assets** in under **60 seconds**. |
| **Compute Speed** | Calculate Hurst Exponent for **10,000 candles** in under **0.05 seconds** (via Numba). |
| **System Latency** | Dashboard load time for a new ticker < **200ms**. |
| **Operational Cost** | **$0.00**. No cloud servers, no SaaS subscriptions (using free tier APIs). |

---

## 3. Product Scope (Phasing)

### 3.1 MVP (Minimum Viable Product)
* **Focus:** Data Pipeline & Math Core.
* **Features:** Async data fetching, DuckDB storage, FFT Cycle Detector, Numba-optimized Hurst Calculator.
* **Output:** Console-based signal generation.

### 3.2 Growth Phase
* **Focus:** Validation & Visuals.
* **Features:** VectorBT backtesting engine, Heatmap optimization, Streamlit Dashboard v1.
* **Output:** Interactive charts with Cycle overlays.

### 3.3 Vision (Future State)
* **Focus:** Automation & Execution.
* **Features:** Live Trading via API, RL Agent optimization, Telegram/Discord notifications.

### 3.4 Out of Scope
* Mobile App development.
* SaaS/Cloud multi-tenant architecture.
* Social trading features.

---

## 4. User Journeys

### Persona 1: The Researcher (Backtesting Strategy)
> **Goal:** Validate if "Cycle Bottoms" are profitable when "Hurst > 0.6".
1.  **Ingest:** User runs `python data_loader.py --symbol BTC-USD --years 5`.
2.  **Verify:** System fetches 5 years of 1m/1h/4h data and stores it in DuckDB (< 30s).
3.  **Simulate:** User configures `backtest_config.json` setting `hurst_threshold` to 0.6.
4.  **Compute:** User runs `python vbt_runner.py`. System utilizes 16 CPU threads to test the strategy across 5 timeframes simultaneously.
5.  **Analyze:** System outputs a Heatmap (HTML) showing the Sharpe Ratio for each timeframe.

### Persona 2: The Trader (Live Monitoring)
> **Goal:** Find a trade setup for the next 4 hours.
1.  **Launch:** User starts the dashboard `streamlit run app.py`.
2.  **Scan:** Dashboard auto-refreshes every 60s. The "Opportunity Scanner" highlights `NVDA` and `ETH` as "Approaching Cycle Bottom".
3.  **Inspect:** User clicks `NVDA`. The main chart loads instantly.
    * **Visual:** Price is touching the bottom of the Sine Wave.
    * **Metric:** Hurst Exponent is displayed as **0.72** (Strong Trend).
4.  **Act:** User confirms the confluence and places a manual buy order on their broker.

---

## 5. Functional Requirements (FR)

### Data Management
* **FR-01:** System must support fetching OHLCV data for Stocks and Crypto from public market data APIs.
* **FR-02:** System must handle at least 50 concurrent assets.
* **FR-03:** System must support 6 distinct timeframes: 1m, 5m, 15m, 1h, 4h, 1d.
* **FR-04:** Data ingestion for multiple assets must run concurrently to meet the 60-second throughput target.
* **FR-05:** Database must enable "upsert" functionality to append new candles without duplicating history.

### Quantitative Core
* **FR-06:** System must calculate the Dominant Cycle Period using FFT (Fast Fourier Transform).
* **FR-07:** System must apply a Low-Pass Filter to smooth out high-frequency noise before cycle detection.
* **FR-08:** System must project the dominant cycle phase forward by at least 20 bars.
* **FR-09:** System must calculate the Hurst Exponent using the R/S (Rescaled Range) method.
* **FR-10:** Hurst calculation for 10,000 candles must complete in under 0.05 seconds.

### Strategy & Backtesting
* **FR-11:** System must allow users to define "Long" and "Short" logic based on Cycle Phase and Hurst Value.
* **FR-12:** Backtesting engine must support parameter sweeping (e.g., testing Hurst threshold from 0.5 to 0.9).
* **FR-13:** System must calculate performance metrics: Total Return, Sharpe Ratio, Max Drawdown, Win Rate.
* **FR-14:** System must export trade logs to CSV for audit.

### User Interface (Dashboard)
* **FR-15:** Dashboard must display an interactive Candlestick chart with zoom, pan, and crosshair.
* **FR-16:** Chart must support overlaying the "Predicted Sine Wave" on top of price action.
* **FR-17:** Dashboard must include a "Scanner Table" sortable by Hurst Exponent.
* **FR-18:** Dashboard must visually indicate "Buy/Sell" signals (e.g., Green/Red markers).

---

## 6. Non-Functional Requirements (NFR)

### Performance
* **NFR-01 (Latency):** Dashboard query response time must be **< 50ms** for cached data.
* **NFR-02 (Throughput):** Backtesting 5 years of 1-minute data for 1 asset must complete in **< 5 seconds**.
* **NFR-03 (Resource):** RAM usage must never exceed **40GB** (leaving 24GB for OS).

### Reliability
* **NFR-04 (Uptime):** Background scheduler must automatically restart on failure.
* **NFR-05 (Error Handling):** All API failures must be logged to `system.log` without crashing the UI.

### Security
* **NFR-06 (Data Privacy):** No user data or trading strategies shall be transmitted to any external server.
* **NFR-07 (Secrets):** API Keys must be stored in a local `.env` file and never hardcoded.

### Maintainability
* **NFR-08 (Code Style):** Code must adhere to PEP-8 standards.
* **NFR-09 (Documentation):** All complex math functions (FFT, Hurst) must have Docstrings.
* **NFR-10 (Testing):** Core mathematical modules must have >90% Unit Test coverage.

---

## 7. Technical Architecture

### 7.1 Tech Stack
| Component | Technology | Justification |
| :--- | :--- | :--- |
| **Backend** | Python 3.10+ | Industry standard for Quant. |
| **Database** | **DuckDB** | OLAP database, extremely fast for time-series, runs in-process. |
| **Math Core** | **SciPy / Numba** | Standard FFT signal processing & JIT optimization. |
| **Backtesting** | **VectorBT** | Vectorized backtesting engine, faster than event-driven engines. |
| **Frontend** | **Streamlit** | Rapid UI development, native Python support. |

### 7.2 Directory Structure
```text
quant_rabbit/
├── data/                   # DuckDB database file & Raw CSVs
├── src/
│   ├── config.py           # Settings (API Keys, Timeframes, Assets)
│   ├── data_loader.py      # Module (Data Ingestion)
│   ├── signals/            # Core Math
│   │   ├── cycles.py       # FFT Algorithm
│   │   ├── fractals.py     # Hurst Algorithm (Numba)
│   │   └── filters.py      # Hybrid Logic
│   ├── backtest/           # Research Engine
│   │   ├── vbt_runner.py   # VectorBT setup
│   │   └── analyzer.py     # Performance Metrics
│   ├── dashboard/          # UI
│   │   ├── app.py          # Main Streamlit App
│   │   └── charts.py       # Plotly components
├── main.py                 # Entry point
└── requirements.txt