# ORACLE-NBA — Work Plan (Executable)

## Open Data Sources (selected)

| Source | Type | Coverage | Notes |
|--------|------|----------|-------|
| **ESPN Scoreboard API** | Free HTTP | Current + historical by date | Already used; no key |
| **llimllib/nba_data** | Parquet + DuckDB | 2009–present | https://basketball-data.billmill.org/nba/ |
| **nba_api** (swar) | Python client | stats.nba.com | No key; rate limits |
| **sportsdataverse** | Parquet releases | PBP, schedules 2002– | GitHub releases |
| **Kaggle NBA box scores** | CSV | 1947–today | Good for long history |
| **Polymarket / Kalshi** | Prediction markets | Live + recent | For market probs / +EV |

Primary path for Phase 1: **ESPN bulk by date** + **billmill parquet games** when available.

---

## Phases

### Phase 0 — Repo & baseline (DONE)
- [x] GitHub repo `ORACLE-NBA`
- [x] README + methodology + risk rules
- [x] LSTM skeleton, EV, Kelly modules
- [x] Model eval notes (v1.5)

### Phase 1 — Data foundation (IN PROGRESS)
- [ ] Multi-season game log collector (ESPN + optional parquet)
- [ ] Clean schema: date, home, away, score, rest, B2B
- [ ] Store as parquet/CSV under `data/processed/`
- [ ] Feature builder: Elo state, Net Rating, sequences for LSTM

### Phase 2 — Models
- [ ] Harden Elo + Net Rating walk-forward
- [ ] Train XGBoost on tabular features
- [ ] Train LSTM on sequences (walk-forward blocks)
- [ ] Ensemble + calibration

### Phase 3 — +EV engine
- [ ] Odds ingestion (ESPN / Polymarket / Kalshi)
- [ ] De-vig + EV filter
- [ ] Fractional Kelly sizer + bankroll caps

### Phase 4 — Backtest & risk
- [ ] Full walk-forward PnL with vig assumption
- [ ] Circuit breakers (daily/weekly/monthly)
- [ ] Paper-trading log format

### Phase 5 — Ops
- [ ] Daily runner script
- [ ] Decay monitoring
- [ ] Optional Telegram alerts

---

## Success gates before real capital
1. Walk-forward ROI > 0 after ~5% vig over ≥1 full season
2. Max DD within stop rules
3. Calibration stable on recent hold-out
4. No look-ahead in audit
