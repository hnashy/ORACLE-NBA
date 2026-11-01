# ORACLE-NBA

**Quantitative NBA Betting System**  
Positive Expected Value (EV) identification with strict risk management and long-term edge over the market.

> Research / educational use only. Not financial advice. Past performance does not guarantee future results.

**Repository:** https://github.com/hnashy/ORACLE-NBA

---

## Goal

Build a production-grade quantitative model that continuously identifies **+EV** bets, applies disciplined bankroll management, and aims for positive net return after vig over ≥12 months while surviving drawdowns.

---

## Methodology

1. **Data** – Historical games, team/player stats, rest, B2B, injuries, market odds (ESPN + prediction markets).
2. **Feature Engineering** – Elo (home/away), Net Rating (rolling), rest differential, B2B flags, pace, form, matchup differentials.
3. **Models**
   - Baseline: Adaptive Elo + Net Rating ensemble (calibrated)
   - ML: XGBoost / LightGBM on engineered features
   - Deep Learning: LSTM / sequence models on recent form sequences
4. **Probability → Edge** – Convert model outputs to well-calibrated probabilities, compare to market-implied (de-vigged) probabilities, compute EV.
5. **Sizing** – Fractional Kelly (typically 0.25–0.5×) with hard caps (0.5–1.5% of bankroll per bet).
6. **Backtesting** – Strict walk-forward, no look-ahead, realistic vig, latency, and limits simulation.
7. **Risk** – Daily / weekly / monthly stop-loss rules, model-decay monitoring, diversification constraints.
8. **Operations** – Periodic retrain, performance dashboards, alert on decay.

---

## Current Status (v1.5 baseline)

| Metric (walk-forward ~1050 games) | Value |
|-----------------------------------|-------|
| Accuracy (favorite)               | ~66.7% |
| Brier Score                       | ~0.425 |
| High-confidence (≥68%) hit rate   | ~74.9% |
| Margin correlation                | ~0.44  |

Baseline is solid but still under-predicts large margins and lacks injury/market-odds integration and deep sequence modeling.

---

## Roadmap

### Phase 1 – Foundation (current)
- [x] Adaptive Elo + Net Rating + Platt calibration
- [x] Walk-forward backtest framework
- [x] Client-side daily predictor (HTML)
- [ ] Full historical data pipeline + market odds

### Phase 2 – Machine Learning
- [ ] XGBoost / LightGBM on rich feature set
- [ ] Proper calibration (isotonic / Platt on out-of-fold)
- [ ] Feature importance & ablation studies

### Phase 3 – Deep Learning
- [ ] LSTM / GRU on rolling team sequences (last N games)
- [ ] Optional Transformer encoder for matchup context
- [ ] Ensemble of Elo + XGB + LSTM with learned or Brier-based weights

### Phase 4 – +EV & Risk Engine
- [ ] Live odds ingestion + de-vig
- [ ] EV filter + fractional Kelly sizer
- [ ] Drawdown circuit breakers
- [ ] Paper-trading / forward-test log

### Phase 5 – Production
- [ ] Scheduled daily run + Telegram / dashboard alerts
- [ ] Model decay monitoring & auto-retrain triggers
- [ ] Multi-sport expansion (optional)

---

## Project Structure

```
ORACLE-NBA/
├── README.md
├── requirements.txt
├── config/
│   └── default.yaml
├── data/
│   ├── raw/
│   └── processed/
├── src/
│   ├── data/
│   │   ├── collect.py
│   │   └── features.py
│   ├── models/
│   │   ├── elo.py
│   │   ├── net_rating.py
│   │   ├── xgb_model.py
│   │   ├── lstm_model.py
│   │   └── ensemble.py
│   ├── betting/
│   │   ├── odds.py
│   │   ├── ev.py
│   │   └── kelly.py
│   ├── backtest/
│   │   ├── walk_forward.py
│   │   └── metrics.py
│   └── risk/
│       └── circuit_breaker.py
├── notebooks/
├── web/
│   └── ORACLE-NBA-Daily.html
└── tests/
```

---

## Risk Rules (default)

- Max risk per bet: **1.0%** of bankroll (hard cap 1.5%)
- Fractional Kelly: **0.25–0.5×**
- Daily stop-loss: **-3%** of bankroll
- Weekly stop-loss: **-6%**
- Monthly stop-loss: **-12%**
- Minimum model confidence / EV threshold before betting
- No parlays by default (single bets only for edge purity)

---

## Success Criteria

- Positive net ROI after vig over a rolling 12-month window
- Drawdowns survivable under the risk rules above
- Calibration and edge stable (no rapid decay without retrain)
- Walk-forward and out-of-sample results consistent with live paper performance

---

## Disclaimer

This project is for **research and educational purposes only**.  
It is **not** betting advice. Sports betting involves substantial risk of loss.  
Use only capital you can afford to lose and comply with local laws.

---

## License

MIT
