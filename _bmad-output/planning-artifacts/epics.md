---
stepsCompleted: [1, 2, 3, 4]
lastStep: 4
status: 'complete'
completedAt: '2026-02-13'
inputDocuments:
  - prd.md
  - _bmad-output/planning-artifacts/architecture.md
---

# rabbit-quant - Epic Index

## Overview

This document serves as the master index for all Epics and Stories in the project.

Detailed breakdowns for each Epic are located in the `stories/` directory.

## Requirements Inventory

The detailed list of Functional (FR) and Non-Functional (NFR) requirements is maintained in [architecture.md](architecture.md).

## Epic Index

### [Epic 1: Data Acquisition & Storage](stories/epic-01-data.md)
Users can ingest and store multi-asset OHLCV data from stock and crypto markets, ready for analysis.
- **Stories:** 1.1 - 1.5
- **Status:** COMPLETE ✅

### [Epic 2: Quantitative Signal Generation](stories/epic-02-signals.md)
Users can detect dominant market cycles and measure trend persistence (Hurst) to identify high-probability turning points.
- **Stories:** 2.1 - 2.5
- **Status:** COMPLETE ✅

### [Epic 3: Strategy Backtesting & Optimization](stories/epic-03-backtest.md)
Users can validate trading hypotheses by backtesting cycle+Hurst strategies with parameter optimization and detailed performance reports.
- **Stories:** 3.1 - 3.6
- **Status:** COMPLETE ✅

### [Epic 4: Interactive Trading Dashboard](stories/epic-04-dashboard.md)
Users can visually monitor markets in real-time, scan for opportunities by Hurst ranking, and see buy/sell signals on interactive charts with cycle overlays.
- **Stories:** 4.1 - 4.9
- **Status:** COMPLETE ✅

### [Epic 5: Live Paper Trading System](stories/epic-05-paper-trading.md)
Users can test strategies in real-time with a simulated portfolio, tracking PnL without risking real capital.
- **Stories:** 5.1 - 5.5
- **Status:** PENDING ⏳
