# Model Re-Evaluation & LSTM Plan

## Baseline (v1.5) – Walk-forward ~1,049 games (2025-26 season)

| Metric | Value | Comment |
|--------|-------|--------|
| Accuracy (favorite) | **66.7%** | Competitive for NBA |
| Brier | **0.425** | Acceptable; room to improve |
| Log Loss | **0.616** | |
| High-conf (≥68%) hit | **74.9%** | Strong separation |
| Margin correlation | **0.44** | Still under-predicts large margins |
| Mean \|pred margin\| | 8.0 vs actual 13.3 | Conservative |

### Strengths
- Clean walk-forward (no look-ahead)
- Confidence buckets behave correctly
- Calibration improved after Platt scaling
- B2B / rest effects included

### Gaps vs quant goal
1. No market odds → cannot compute true +EV yet
2. No injury / lineup features
3. Margin still conservative
4. No sequence model (form momentum beyond simple net rating)
5. No XGBoost / deep ensemble
6. No realistic vig / limits / latency in backtest PnL

---

## Deep Learning Addition (LSTM)

### Design
- **Input**: last 10 games for home + last 10 for away
  - Features per game: margin, pts_for, pts_against, rest, B2B, is_home
- **Architecture**: dual-stream LSTM → concat final hidden → MLP → P(home win)
- **Training**: walk-forward only (train on past, validate on next block)
- **Role**: capture short-term form / momentum that Elo smooths out

### Integration
```
P_final = w_elo * P_elo + w_xgb * P_xgb + w_lstm * P_lstm
```
Weights from inverse Brier (or learned on a hold-out).

### Expected benefit
- Better handling of hot/cold streaks
- Slight lift in high-confidence accuracy
- Better margin estimates when form diverges from long-term Elo

### Risks
- Overfitting on small sequences → strong regularization + early stopping
- Data leakage if sequences include future games → strict `as_of_ts` filter

---

## Next concrete steps

1. **Data pipeline** – bulk historical games + closing odds (or proxy from prediction markets)
2. **Feature store** – Elo, Net Rating, rest, B2B, sequence tensors for LSTM
3. **Train LSTM** walk-forward and measure lift vs Elo-only
4. **XGB baseline** on tabular features
5. **Ensemble + calibration**
6. **+EV layer** – de-vig market odds, EV filter, fractional Kelly
7. **Risk engine** – circuit breakers, paper-trading log
8. **Forward test** – at least one full season paper before any real capital

---

## Success gate before real money

- Walk-forward + out-of-sample ROI > 0 after 5% vig assumption
- Max drawdown within configured stop rules
- Calibration plot close to diagonal on recent seasons
- No look-ahead or survivorship artifacts in audit
