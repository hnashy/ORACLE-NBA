# Model Re-Evaluation & LSTM Results

## Baseline Elo+Net (v1.5) – 2 seasons (~2497 games)

| Metric | Value |
|--------|-------|
| Accuracy | **66.5–67.8%** |
| Brier (home) | ~0.21 |
| High-conf (≥68%) hit | **~75–76%** |

---

## LSTM Walk-Forward (OOS blocks, n=1497)

Retrain every 250 games; train only on past; early stopping on val loss.

| Model | Accuracy | Brier | LogLoss | High≥68% hit |
|-------|----------|-------|---------|--------------|
| **Elo+Net** | **67.8%** | **0.209** | 0.606 | 76.2% (n=762) |
| LSTM only | 64.7% | 0.221 | 0.633 | 77.2% (n=408) |
| **Ensemble 55% Elo + 45% LSTM** | 67.6% | **0.209** | **0.605** | **79.3%** (n=581) |

### Interpretation
- LSTM alone is weaker overall (less data + short sequences) but competitive in high-confidence subset.
- Ensemble **preserves Elo accuracy** and **improves high-confidence hit rate** (79.3% vs 76.2%).
- LogLoss slightly better for ensemble → better probability quality for EV/Kelly later.

### Design notes
- Input: last 10 games × 6 features (margin, pts_for/against, rest, B2B, is_home) for home and away.
- Dual-stream LSTM → concat → MLP → P(home).
- Strict `as_of_ts` filter (no look-ahead).
- Regularization: dropout 0.25, weight decay, early stopping.

---

## Gaps still open
1. No market odds → no true +EV yet
2. No injury / lineup features
3. No XGBoost tabular model yet
4. Margin still conservative
5. No vig / limits simulation in PnL backtest

---

## Next steps
1. XGBoost on tabular features (Elo diff, net diff, rest, B2B, …)
2. Odds layer (Polymarket/Kalshi or ESPN when available) → EV + Kelly
3. Full bankroll simulation with stop-loss rules
4. Paper-trading log

## Success gate before real capital
- Walk-forward ROI > 0 after ~5% vig over ≥1 full season
- Max DD within stop rules
- Calibration stable
- No look-ahead in audit
