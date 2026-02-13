# Development Roadmap — Quant-Rabbit Local Core

**Project:** rabbit-quant
**Created:** 2026-02-13
**Status:** Planning Complete — Ready for Implementation

---

## Phase Overview

| Phase | Name | Focus | Status |
|-------|------|-------|--------|
| 0 | Project Scaffold | Environment, config, tooling | Not Started |
| 1 | Data Pipeline (MVP-a) | Data ingestion + DuckDB storage | Not Started |
| 2 | Math Engine (MVP-b) | FFT cycles + Hurst exponent | Not Started |
| 3 | Backtest Engine (Growth-a) | VectorBT + parameter sweeps | Not Started |
| 4 | Dashboard (Growth-b) | Streamlit UI + Plotly charts | Not Started |
| 5 | Integration & Polish | End-to-end flow, scheduler, testing | Not Started |

---

## Phase 0: Project Scaffold

**Goal:** Establish project foundation all modules depend on.

**Deliverables:**
- `uv init` with Python 3.10, `pyproject.toml` configured
- Full directory structure per architecture doc
- `src/config.py` — Pydantic Settings + TOML loaders
- `.env.example`, `config/*.toml` templates
- `main.py` entry point skeleton (CLI: fetch, backtest, dashboard)
- Pre-commit hooks (ruff), pytest configuration
- loguru logging setup

**Dependencies:** None
**Risk:** Low
**FRs Addressed:** Cross-cutting config foundation

---

## Phase 1: Data Pipeline (MVP-a)

**Goal:** Async multi-asset OHLCV ingestion into DuckDB.

**Deliverables:**
- `src/data_loader.py` — async fetching via yfinance (stocks) + ccxt (crypto)
- DuckDB schema: `ohlcv` table with upsert semantics
- Support 50+ concurrent assets, 6 timeframes
- Rate limiting + retry with exponential backoff
- `main.py fetch` CLI command functional
- Unit tests with fixture data (no live API in tests)

**Dependencies:** Phase 0
**Risk:** Medium — API rate limits, data format inconsistencies
**FRs Addressed:** FR-01, FR-02, FR-03, FR-04, FR-05
**NFRs Addressed:** NFR-04, NFR-05, NFR-06, NFR-07

**Success Criteria:**
- 50+ assets fetched and stored in < 60 seconds
- Upsert correctly avoids duplicates
- Graceful handling of API failures (logged, not crashed)

---

## Phase 2: Math Engine (MVP-b)

**Goal:** Core quantitative signal generation — FFT cycles + Hurst exponent.

**Deliverables:**
- `src/signals/cycles.py` — FFT dominant cycle detection + low-pass filter + forward projection
- `src/signals/fractals.py` — Numba-optimized Hurst R/S calculation
- `src/signals/filters.py` — Combined cycle phase + Hurst signal generation
- All hot-path functions use `@numba.njit` with numpy-only internals
- Wrapper functions handle pandas-to-numpy boundary conversions
- Math tests against known analytical results (>90% coverage)

**Dependencies:** Phase 0 (config), Phase 1 (data to compute on)
**Risk:** Medium — Numba compatibility constraints, FFT tuning
**FRs Addressed:** FR-06, FR-07, FR-08, FR-09, FR-10
**NFRs Addressed:** NFR-02, NFR-03, NFR-10

**Success Criteria:**
- Hurst for 10K candles < 0.05s
- FFT correctly identifies dominant cycle in synthetic sinusoidal data
- Hurst returns ~0.5 for white noise, ~0.7+ for trending series

---

## Phase 3: Backtest Engine (Growth-a)

**Goal:** VectorBT-powered backtesting with parameter optimization.

**Deliverables:**
- `src/backtest/vbt_runner.py` — VectorBT setup, long/short signal logic, parameter sweep engine
- `src/backtest/analyzer.py` — Sharpe Ratio, Max Drawdown, Win Rate, Total Return
- CSV trade log export
- `main.py backtest` CLI command functional
- Heatmap output for parameter sweep results

**Dependencies:** Phase 2 (signals to backtest)
**Risk:** Medium — VectorBT API complexity, memory for large sweeps
**FRs Addressed:** FR-11, FR-12, FR-13, FR-14
**NFRs Addressed:** NFR-02, NFR-03

**Success Criteria:**
- 5yr 1m data backtest < 5 seconds
- Parameter sweep produces valid Sharpe heatmap
- CSV export matches executed trades exactly
- RAM stays under 40GB during large sweeps

---

## Phase 4: Dashboard (Growth-b)

**Goal:** Interactive Streamlit dashboard with real-time scanner.

**Deliverables:**
- `src/dashboard/app.py` — Main app, page routing, scanner table (sortable by Hurst)
- `src/dashboard/charts.py` — Plotly candlestick with sine wave overlay + buy/sell markers
- In-memory DataFrame cache with TTL for < 50ms query response
- Auto-refresh scanner (60s interval)

**Dependencies:** Phase 2 (signals for display), Phase 3 (backtest results optional)
**Risk:** Medium — Streamlit single-threaded constraints, chart performance
**FRs Addressed:** FR-15, FR-16, FR-17, FR-18
**NFRs Addressed:** NFR-01, NFR-03, NFR-05

**Success Criteria:**
- Dashboard load < 200ms for cached ticker
- Scanner correctly sorts by Hurst value
- Sine wave overlay visually aligns with price action
- Buy/sell markers render at correct timestamps

---

## Phase 5: Integration & Polish

**Goal:** End-to-end system working as a cohesive product.

**Deliverables:**
- APScheduler background data refresh (auto-restart on failure)
- End-to-end integration tests (fetch → compute → display)
- Memory profiling and optimization (psutil monitoring)
- OHLCV data validation before DuckDB insert
- README with setup instructions and usage guide
- Final test coverage report (>90% on math modules)

**Dependencies:** All previous phases
**Risk:** Low — integration issues, edge cases
**NFRs Addressed:** NFR-04, NFR-08, NFR-09, NFR-10

**Success Criteria:**
- System runs continuously without crashes for 24h
- All success metrics from PRD Section 2 met
- Test coverage >90% on signals/ modules

---

## Dependency Graph

```
Phase 0 (Scaffold)
    ├──→ Phase 1 (Data Pipeline)
    │       └──→ Phase 2 (Math Engine)
    │               ├──→ Phase 3 (Backtest)
    │               └──→ Phase 4 (Dashboard)
    │                       │
    └───────────────────────┴──→ Phase 5 (Integration)
```

Note: Phase 3 and Phase 4 can be developed in parallel after Phase 2 completes.

---

## Out of Scope (Future — Vision Phase)

- Live trading API integration
- RL Agent optimization
- Telegram/Discord notifications
- Docker containerization
- CI/CD pipeline
