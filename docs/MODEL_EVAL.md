# Model Evaluation — Elo / XGBoost / LSTM

Walk-forward on 2 NBA seasons (~2497 games). All models train only on past data.

## Out-of-sample comparison (n=1497)

| Model | Accuracy | Brier | LogLoss | High≥68% hit |
|-------|----------|-------|---------|--------------|
| **Elo+Net (v1.5)** | **67.8%** | **0.209** | 0.606 | 76.2% (n=762) |
| XGBoost | 66.7% | 0.214 | 0.618 | 77.6% (n=572) |
| LSTM only | 64.7% | 0.221 | 0.633 | 77.2% (n=408) |
| Ensemble 50% Elo + 50% XGB | 67.4% | 0.209 | 0.605 | 77.6% (n=657) |
| Ensemble 55% Elo + 45% LSTM | 67.6% | 0.209 | 0.605 | 79.3% (n=581) |
| **Triple Elo+XGB+LSTM** | 67.3% | **0.209** | **0.605** | **79.3%** (n=603) |

### Takeaways
- **Elo remains the strongest single model** on accuracy and Brier.
- XGBoost and LSTM add value mainly in **high-confidence** regions and slight LogLoss improvement when ensembled.
- Triple ensemble matches best LogLoss and best high-conf hit rate → preferred for betting filters (+EV / Kelly).

### XGBoost top features (gain)
1. `net_diff`
2. `elo_margin_pts`
3. `elo_diff`
4. `h_b2b`
5. rest / Elo levels

---

## Architecture summary

| Component | Role |
|-----------|------|
| Adaptive Elo + Net Rating | Long-term strength + recent form |
| XGBoost | Non-linear tabular interactions |
| LSTM | Short sequence momentum (last 10 games) |
| Platt-style calibration | Reduce overconfidence |
| Ensemble weights | ~45% Elo / 35% XGB / 20% LSTM (tunable) |

---

## Still missing for +EV system
1. Market odds (de-vig) → true EV
2. Injury / lineup features
3. Bankroll simulation + stop-loss rules
4. Paper-trading log

## Next
1. Odds layer (Polymarket / Kalshi / ESPN) + EV filter + fractional Kelly
2. Full risk simulation
3. Paper forward test

## Success gate before real capital
- Walk-forward ROI > 0 after ~5% vig over ≥1 full season
- Max DD within stop rules
- Calibration stable / no look-ahead
