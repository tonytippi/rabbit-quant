---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# Epic 2: Quantitative Signal Generation

Users can detect dominant market cycles and measure trend persistence (Hurst) to identify high-probability turning points.

## Stories

### Story 2.1: FFT Dominant Cycle Detection

As a **quant researcher**,
I want to detect the dominant cycle period in price data using FFT,
So that I can identify recurring market rhythms for timing entries/exits.

**Acceptance Criteria:**

**Given** a numpy array of close prices (minimum 256 data points)
**When** I call the cycle detection function
**Then** it returns the dominant cycle period (in bars) using Fast Fourier Transform
**And** the function has a docstring explaining the FFT methodology

**Given** a synthetic sinusoidal input with known period (e.g., 50 bars)
**When** FFT analysis runs
**Then** the detected dominant period matches the known period within 5% tolerance

**Given** close price data from DuckDB
**When** the wrapper function is called with a DataFrame
**Then** it converts to numpy, calls the @njit function, and returns the result
**And** the @njit function uses only numpy operations (no pandas, no Python objects)

### Story 2.2: Low-Pass Filter for Noise Smoothing

As a **quant researcher**,
I want high-frequency noise removed from price data before cycle detection,
So that the dominant cycle signal is cleaner and more reliable.

**Acceptance Criteria:**

**Given** a numpy array of close prices with mixed frequency components
**When** I apply the low-pass filter
**Then** high-frequency noise is attenuated while preserving the dominant cycle
**And** the cutoff frequency is configurable via `config/strategy.toml`

**Given** a synthetic signal with a known dominant cycle plus random noise
**When** the filter is applied before FFT
**Then** cycle detection accuracy improves compared to unfiltered data

**Given** the filter function
**When** I inspect its implementation
**Then** it has a docstring explaining the filtering approach and parameters

### Story 2.3: Forward Cycle Phase Projection

As a **quant researcher**,
I want the detected cycle projected forward by at least 20 bars,
So that I can anticipate upcoming cycle tops and bottoms.

**Acceptance Criteria:**

**Given** a detected dominant cycle period and current phase
**When** I call the projection function
**Then** it returns a phase array extending at least 20 bars into the future
**And** the projection is represented as a sine wave with the detected period

**Given** historical data where the cycle was detected
**When** the forward projection is generated
**Then** the projection smoothly continues from the last known phase
**And** the output includes both the historical fit and the forward projection

**Given** the projection output
**When** consumed by downstream modules (backtest or dashboard)
**Then** it is returned as a dict containing `dominant_period`, `phase_array`, and `projection_array`

### Story 2.4: Numba-Optimized Hurst Exponent

As a **quant researcher**,
I want to calculate the Hurst Exponent using the R/S method with Numba JIT,
So that I can measure trend persistence at high speed.

**Acceptance Criteria:**

**Given** a numpy array of 10,000 close prices
**When** I call the Hurst calculation function
**Then** it completes in under 0.05 seconds
**And** the function uses `@numba.njit` with numpy-only internals

**Given** white noise (random walk) input data
**When** Hurst is calculated
**Then** the result is approximately 0.5 (within 0.1 tolerance)

**Given** a strongly trending synthetic series
**When** Hurst is calculated
**Then** the result is approximately 0.7+ indicating persistent trend

**Given** the Hurst function
**When** I inspect it
**Then** it has a docstring explaining the R/S (Rescaled Range) method
**And** a wrapper function accepts DataFrame input and returns a float

### Story 2.5: Combined Signal Generation

As a **quant researcher**,
I want cycle phase and Hurst value combined into actionable trading signals,
So that I can identify high-probability turning points with trend confirmation.

**Acceptance Criteria:**

**Given** a symbol with OHLCV data in DuckDB
**When** I run signal generation via `signals/filters.py`
**Then** it reads data, computes cycle (Stories 2.1-2.3) and Hurst (Story 2.4), and returns a combined signal dict

**Given** the combined signal output
**When** I inspect its structure
**Then** it contains: `symbol`, `timeframe`, `dominant_period`, `current_phase`, `hurst_value`, `phase_array`, `projection_array`, `signal` (long/short/neutral)

**Given** configurable thresholds in `config/strategy.toml` (e.g., `hurst_threshold = 0.6`)
**When** signals are generated
**Then** the signal logic uses these thresholds to determine long/short/neutral

**Given** the signal generation is run for multiple assets
**When** using ProcessPoolExecutor for batch compute
**Then** all assets are processed in parallel across available CPU cores
