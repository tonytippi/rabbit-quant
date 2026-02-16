---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
workflowType: 'architecture'
project_name: 'rabbit-quant'
user_name: 'Tony'
date: '2026-02-13'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (18 total):**
- **Data Management (5):** Async multi-asset OHLCV ingestion, 50+ concurrent assets, 6 timeframes, upsert semantics in DuckDB
- **Quantitative Core (5):** FFT cycle detection with low-pass filtering, forward cycle projection (20+ bars), Numba-optimized Hurst Exponent (<0.05s for 10K candles)
- **Strategy & Backtesting (4):** Configurable long/short logic on cycle phase + Hurst, parameter sweep engine, performance metrics (Sharpe/Drawdown/WinRate), CSV trade log export
- **User Interface (4):** Interactive candlestick charts (Plotly), sine wave overlay, scanner table sortable by Hurst, buy/sell signal markers

**Non-Functional Requirements (10 total):**
- **Performance:** <50ms cached query, <5s backtest for 5yr 1m data, <200ms dashboard load, 40GB RAM cap
- **Reliability:** Auto-restart scheduler, graceful API failure handling with logging
- **Security:** Zero external data transmission, .env-based secrets management
- **Maintainability:** PEP-8, docstrings on math functions, >90% test coverage on core math

**Scale & Complexity:**
- Primary domain: Backend/Data-Science desktop application with web UI
- Complexity level: Medium (compute-intensive, single-user)
- Estimated architectural components: 6 (Data Pipeline, Math Engine, Backtest Engine, Dashboard, Configuration, Scheduler)

### Technical Constraints & Dependencies

- **Hardware-bound:** Targets AMD Ryzen 7 7735HS (8C/16T), 64GB DDR5 — architecture must exploit multi-core parallelism
- **In-process database:** DuckDB runs embedded, no server process — simplifies deployment, limits concurrent write patterns
- **Numba JIT:** Requires numba-compatible code patterns in hot paths (no arbitrary Python objects)
- **Free-tier APIs:** Data sources must be public/free — rate limiting and retry logic required
- **Streamlit constraints:** Single-threaded event loop, stateful sessions — long-running compute must be offloaded

### Cross-Cutting Concerns Identified

- **Memory management:** 40GB budget shared across data loading, DuckDB, backtest vectorization, and dashboard state
- **Concurrency model:** asyncio for I/O-bound data fetching vs multiprocessing for CPU-bound math — need clear boundary
- **Configuration propagation:** Asset lists, timeframes, thresholds flow through every layer — centralized config needed
- **Error resilience:** API failures must not crash pipeline; partial data must be handled gracefully
- **Observability:** Logging strategy for debugging math outputs and data quality issues

## Starter Template Evaluation

### Primary Technology Domain

Python 3.10+ data-science/quant desktop application with embedded web UI (Streamlit)

### Starter Options Considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Cookiecutter Data Science v2 | Standard DS structure, well-maintained | Too generic, notebook-focused, unused dirs | Rejected |
| Quant Trading Project Structure | Quant-specific | Niche, not well-maintained, doesn't match stack | Rejected |
| `uv init` + custom PRD structure | Modern tooling, exact fit, no bloat | Requires manual scaffold | **Selected** |

### Selected Starter: `uv` (v0.10.2) + Custom Structure

**Rationale:** PRD already defines optimal directory structure for this project. Modern `uv` package manager provides fast dependency resolution, lock files, and Python version management. No template bloat.

**Initialization Command:**

```bash
uv init rabbit-quant --python 3.10
cd rabbit-quant
```

**Architectural Decisions Provided by Starter:**

**Language & Runtime:**
- Python 3.10+ managed via `uv` with `.python-version` pin
- `pyproject.toml` for all project config (PEP-621)

**Dependency Management:**
- `uv` for package installation and resolution (10-100x faster than pip)
- `uv.lock` for reproducible builds

**Build Tooling:**
- No build system needed (application, not library)
- `uv run` for script execution with automatic venv management

**Testing Framework:**
- pytest (to be configured in pyproject.toml)
- >90% coverage target on math modules per NFR-10

**Code Quality:**
- ruff for linting + formatting (PEP-8 per NFR-08)
- pre-commit hooks

**Code Organization:**
- Flat `src/` layout matching PRD section 7.2
- Modules: config, data_loader, signals/, backtest/, dashboard/

**Note:** Project initialization using `uv init` should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Data sources: yfinance (stocks) + ccxt (crypto)
- DuckDB schema: single table with symbol/timeframe columns
- Concurrency model: asyncio (I/O) + Numba parallel (math) + ProcessPoolExecutor (batch)

**Important Decisions (Shape Architecture):**
- Config: Pydantic Settings (.env) + TOML (asset/strategy definitions)
- Logging: loguru with file rotation
- Scheduler: APScheduler for background data refresh
- Caching: in-memory DataFrame cache with TTL in dashboard layer

**Deferred Decisions (Post-MVP):**
- Live trading API integration
- Docker containerization
- CI/CD pipeline
- Telegram/Discord notifications

### Data Architecture

| Decision | Choice | Version | Rationale |
|----------|--------|---------|-----------|
| Stock data | yfinance | latest | Free, no API key, covers stocks/ETFs |
| Crypto data | ccxt | latest | Unified exchange API, all timeframes |
| Database | DuckDB | latest | PRD requirement, in-process OLAP |
| Schema | Single table | — | Symbol+timeframe columns, DuckDB handles filtering efficiently |
| Dashboard cache | In-memory DataFrame | — | TTL-based, meets <50ms query target |

### Concurrency & Compute

| Layer | Pattern | Scope |
|-------|---------|-------|
| Data fetching | asyncio + aiohttp | data_loader module (Writer Service) |
| Signal math | Numba @njit(parallel=True) | signals/ modules |
| Batch compute | ProcessPoolExecutor | backtest/ multi-asset jobs |
| Dashboard | Streamlit event loop | dashboard/ (Reader Only) |

**Boundary rule:** asyncio never enters signals/. Numba never enters data_loader. ProcessPoolExecutor orchestrates multi-asset signal computation.

### Production Deployment Strategy

**Writer Service Pattern:**
To solve DuckDB's single-writer limitation in server environments, the system splits into two distinct processes:
1.  **Writer Service (`run-scheduler`):** A standalone daemon that owns the write lock. It executes `fetch_all_assets` on a schedule (e.g., every 5 minutes).
2.  **Reader App (`dashboard`):** The Streamlit application that connects to DuckDB in `read_only=True` mode. It never writes to the database.

**Local Workstation vs. Server:**
- **Local:** `main.py fetch` runs on-demand. `main.py dashboard` runs independently. Conflicts handled by user serialization.
- **Server:** `main.py run-scheduler` runs continuously in background. `main.py dashboard` serves UI.

### Configuration & Observability

| Decision | Choice | Rationale |
|----------|--------|-----------|
| App config | Pydantic Settings | Typed .env loading, validation |
| Strategy config | TOML files | Human-editable asset lists, thresholds |
| Logging | loguru | Simple API, rotation, desktop-friendly |
| Scheduler | APScheduler | Cron patterns, auto-restart (NFR-04) |

### Infrastructure & Deployment

- **Runtime:** Local only, no cloud
- **Package management:** uv (lock file for reproducibility)
- **No Docker** for MVP
- **No CI/CD** for MVP — local pytest + ruff pre-commit
- **Future:** Makefile/justfile for common commands

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Python Code:** PEP-8 snake_case everywhere
- Functions: `calculate_hurst_exponent()`, `fetch_ohlcv_data()`
- Variables: `dominant_cycle_period`, `hurst_value`
- Classes: PascalCase — `CycleDetector`, `DataLoader`
- Constants: UPPER_SNAKE — `MAX_RAM_GB`, `DEFAULT_TIMEFRAMES`
- Private: single underscore prefix — `_validate_candles()`

**DuckDB:**
- Table: `ohlcv` (singular, lowercase)
- Columns: snake_case — `symbol`, `timeframe`, `open_price`, `close_price`, `volume`, `timestamp`
- No abbreviated names — `timestamp` not `ts`, `volume` not `vol`

**TOML Config Keys:** snake_case matching Python variables
- `hurst_threshold = 0.6`
- `default_timeframes = ["1m", "5m", "15m", "1h", "4h", "1d"]`

**Files:** snake_case matching module names — `data_loader.py`, `vbt_runner.py`, `cycle_detector.py`

### Data Flow Patterns

**Inter-module data contract:**

| From → To | Format | Why |
|-----------|--------|-----|
| data_loader → DuckDB | pandas DataFrame | DuckDB native insert |
| DuckDB → signals/ | numpy ndarray (via `.values`) | Numba requires numpy |
| signals/ → backtest/ | dict of numpy arrays | VectorBT input format |
| signals/ → dashboard/ | pandas DataFrame | Plotly/Streamlit native |
| config → all modules | Pydantic model instances | Type-safe, validated |

**Rule:** Each module boundary has ONE canonical data format. No ad-hoc conversions inside modules.

### Module Boundary Rules

| Module | Owns | Does NOT own |
|--------|------|-------------|
| `config.py` | Settings loading, validation, asset lists | Business logic |
| `data_loader.py` | API calls, DuckDB read/write, upsert | Signal computation |
| `signals/cycles.py` | FFT, low-pass filter, cycle projection | Trading decisions |
| `signals/fractals.py` | Hurst exponent calculation | Trading decisions |
| `signals/filters.py` | Combining cycle + Hurst into signals | Backtesting |
| `backtest/vbt_runner.py` | VectorBT setup, parameter sweeps | Signal math |
| `backtest/analyzer.py` | Metrics (Sharpe, Drawdown, WinRate) | Data fetching |
| `dashboard/app.py` | Streamlit layout, page routing | Computation |
| `dashboard/charts.py` | Plotly chart components | Data fetching |

### Error Handling Patterns

**Standard pattern for all modules:**

```python
from loguru import logger

def fetch_data(symbol: str) -> pd.DataFrame | None:
    try:
        result = _do_fetch(symbol)
        return result
    except RateLimitError:
        logger.warning(f"Rate limited for {symbol}, retrying...")
        return _retry_with_backoff(symbol)
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return None  # Partial failure, don't crash pipeline
```

**Rules:**
- Never raise exceptions across module boundaries — return None or empty DataFrame
- Log at appropriate level: `error` for failures, `warning` for retries, `info` for operations, `debug` for math outputs
- Caller handles None/empty returns gracefully

### Numba Compatibility Rules

**In `signals/` hot path functions:**
- Use `@numba.njit` decorator on all compute functions
- Input/output: numpy arrays ONLY (no pandas, no dicts, no strings)
- No Python objects inside njit functions
- Wrapper functions handle pandas↔numpy conversion at boundary

```python
# CORRECT pattern
@numba.njit
def _hurst_rs(prices: np.ndarray) -> float:
    # Pure numpy operations only
    ...

def calculate_hurst(df: pd.DataFrame, column: str = "close_price") -> float:
    """Public API: accepts DataFrame, returns float."""
    return _hurst_rs(df[column].values)
```

### Testing Patterns

- Tests in `tests/` directory mirroring `src/` structure
- Files: `test_cycles.py`, `test_fractals.py`, `test_data_loader.py`
- Use `pytest` with `pytest-cov`
- Math tests: compare against known analytical results (not just "doesn't crash")
- Data tests: use fixtures with sample OHLCV data (no live API calls in tests)

### Enforcement Guidelines

**All AI Agents MUST:**
1. Check module boundary table before adding logic to any file
2. Use the canonical data format at each boundary (see Data Flow table)
3. Never put Numba-incompatible code inside `@njit` functions
4. Return None/empty on errors — never raise across module boundaries
5. Use loguru for all logging, never print()

## Project Structure & Boundaries

### Complete Project Directory Structure

```
rabbit-quant/
├── pyproject.toml              # Project config, dependencies, tool settings (ruff, pytest)
├── uv.lock                     # Reproducible dependency lock
├── .python-version             # Python 3.10 pin
├── .env                        # API keys, secrets (gitignored)
├── .env.example                # Template for .env
├── .gitignore
├── .pre-commit-config.yaml     # ruff hooks
├── README.md
├── main.py                     # Entry point: CLI commands (fetch, backtest, dashboard)
│
├── config/
│   ├── assets.toml             # Asset lists, watchlists
│   ├── strategy.toml           # Hurst thresholds, cycle params, backtest settings
│   └── timeframes.toml         # Timeframe definitions and mappings
│
├── data/                       # DuckDB database file & raw exports
│   └── rabbit.duckdb           # Single DuckDB file (gitignored)
│
├── src/
│   ├── __init__.py
│   ├── config.py               # Pydantic Settings, TOML loaders (FR: config propagation)
│   │
│   ├── data_loader.py          # Async data ingestion: yfinance + ccxt (FR-01→FR-05)
│   │
│   ├── signals/                # Quantitative Core (FR-06→FR-10)
│   │   ├── __init__.py
│   │   ├── cycles.py           # FFT dominant cycle detection + low-pass filter (FR-06, FR-07)
│   │   ├── fractals.py         # Numba-optimized Hurst R/S calculation (FR-09, FR-10)
│   │   └── filters.py          # Cycle phase + Hurst → signal generation (FR-08, FR-11)
│   │
│   ├── backtest/               # Strategy & Backtesting (FR-11→FR-14)
│   │   ├── __init__.py
│   │   ├── vbt_runner.py       # VectorBT setup, parameter sweeps (FR-12)
│   │   └── analyzer.py         # Sharpe, Drawdown, WinRate, CSV export (FR-13, FR-14)
│   │
│   └── dashboard/              # User Interface (FR-15→FR-18)
│       ├── __init__.py
│       ├── app.py              # Streamlit main app, page routing, scanner table (FR-17)
│       └── charts.py           # Plotly candlestick, sine overlay, signal markers (FR-15, FR-16, FR-18)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Shared fixtures: sample OHLCV data, DuckDB in-memory
│   ├── test_config.py
│   ├── test_data_loader.py
│   ├── test_cycles.py          # FFT against known sinusoidal input
│   ├── test_fractals.py        # Hurst against known H values (white noise=0.5, trend=0.7+)
│   ├── test_filters.py
│   ├── test_vbt_runner.py
│   └── test_analyzer.py
│
└── logs/                       # loguru output (gitignored)
    └── rabbit.log
```

### Architectural Boundaries

**Data Flow Diagram:**

```
[External APIs] ──async──→ [data_loader.py] ──DataFrame──→ [DuckDB]
                                                              │
                               ┌──────────────────────────────┘
                               │ numpy ndarray
                               ▼
                          [signals/]
                          cycles.py ──→ dominant_period, phase_array
                          fractals.py ──→ hurst_value
                          filters.py ──→ combined signal dict
                               │
                    ┌──────────┴──────────┐
                    │                     │
              dict of arrays        DataFrame
                    ▼                     ▼
             [backtest/]          [dashboard/]
             vbt_runner.py        app.py + charts.py
             analyzer.py
```

**Module Communication Rules:**
- `data_loader` → DuckDB: ONLY module that writes to database
- `signals/` → reads from DuckDB via numpy arrays, returns numpy/dicts
- `backtest/` → reads signals output, orchestrates VectorBT
- `dashboard/` → reads DuckDB + signals output as DataFrames, NEVER writes data
- `config.py` → imported by all modules, NEVER imports from other src/ modules

### Requirements to Structure Mapping

| FR Category | Files | Key FRs |
|-------------|-------|---------|
| Data Management | `data_loader.py`, `config/assets.toml` | FR-01→FR-05 |
| Quantitative Core | `signals/cycles.py`, `signals/fractals.py`, `signals/filters.py` | FR-06→FR-10 |
| Strategy & Backtesting | `backtest/vbt_runner.py`, `backtest/analyzer.py`, `config/strategy.toml` | FR-11→FR-14 |
| User Interface | `dashboard/app.py`, `dashboard/charts.py` | FR-15→FR-18 |
| Cross-cutting: Config | `src/config.py`, `config/*.toml`, `.env` | All modules |
| Cross-cutting: Logging | loguru configured in `main.py` | NFR-04, NFR-05 |
| Cross-cutting: Scheduler | APScheduler configured in `main.py` | NFR-04 |

### External Integration Points

| Integration | Module | Protocol |
|-------------|--------|----------|
| yfinance API | `data_loader.py` | HTTP via yfinance lib |
| ccxt exchanges | `data_loader.py` | HTTP via ccxt lib |
| DuckDB | `data_loader.py` (write), all (read) | In-process, file-based |
| Streamlit server | `dashboard/app.py` | localhost HTTP |

### Development Workflow

```bash
uv run python main.py fetch          # Run data ingestion
uv run python main.py backtest       # Run backtest
uv run streamlit run src/dashboard/app.py  # Launch dashboard
uv run pytest                         # Run tests
uv run ruff check src/                # Lint
```

## Architecture Validation Results

### Coherence Validation ✅

- All technology choices compatible (Python 3.10+, numba, scipy, duckdb, vectorbt, streamlit)
- Concurrency boundaries clean: asyncio (I/O) | Numba (math) | ProcessPoolExecutor (batch)
- Naming conventions uniform: snake_case across Python, DuckDB, TOML, files
- Data flow contracts explicit at every module boundary
- No contradictory decisions found

### Requirements Coverage ✅

- **18/18 Functional Requirements** mapped to specific files with clear ownership
- **10/10 Non-Functional Requirements** addressed architecturally
- All cross-cutting concerns (config, logging, scheduling, error handling) have defined patterns

### Implementation Readiness ✅

- Every module has defined inputs, outputs, and ownership boundaries
- Numba compatibility rules prevent the most common agent mistake
- Error handling pattern uniform and simple (return None, never raise)
- Test structure mirrors source 1:1 with clear fixture strategy

### Gap Analysis

**No critical gaps.** Minor items addressable during implementation:
- RAM runtime monitoring (psutil) — can add to scheduler loop
- OHLCV data validation before DuckDB insert — lightweight pandas check
- Graceful scheduler shutdown — APScheduler defaults suffice

### Architecture Completeness Checklist

- [x] Project context analyzed, scale assessed, constraints identified
- [x] Technology stack fully specified with versions
- [x] All critical architectural decisions documented with rationale
- [x] Implementation patterns defined for naming, data flow, errors, Numba
- [x] Complete directory structure with FR mapping
- [x] Module boundaries and communication rules established
- [x] Testing strategy defined with coverage targets
- [x] Development workflow commands documented

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High

**Key Strengths:**
- Clean separation of concerns with explicit module boundaries
- Performance-first design (Numba, asyncio, vectorized ops)
- Simple, local-only deployment with zero infrastructure overhead
- Every requirement traceable to a specific file

**First Implementation Priority:**
1. `uv init` + scaffold directory structure
2. `src/config.py` — foundation all modules depend on
3. `src/data_loader.py` — need data before anything else works
4. `src/signals/fractals.py` — smallest math module, good first test of Numba pattern
