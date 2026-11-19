# Injury-Aware Elo — Backtest Comparison (9 paper signals)

> Simulation only. Penalties: Tier-1 Out/Doubtful = −20 Elo · Tier-2 = −5 Elo.  
> Historical injury board for Nov 2026 is **manually curated** from public reports (ESPN live API has no free full history).  
> Live path uses ESPN public injuries endpoint (no API key).

---

## Method

1. Start from static `elo_ratings.json`.
2. For each of the 9 T-10m signals, apply known Out stars on that date.
3. Recompute P(H) with HCA=+100.
4. Compare raw edge vs adjusted edge vs market vs paper outcome.

---

## Results table

| Date | Match | Side | Mkt p(H) | Raw p(H) | Raw edge | Adj p(H) | Adj edge | Alert after? | Paper | Injury note |
|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| 11-03 | TOR @ LAC | HOME | 33.6% | 66.8% | **+33.2%** | 62.9% | **+29.3%** | yes | **loss** | LAC: Beal+Ingram+… (−50); TOR: Kawhi (−20) |
| 11-03 | MIA @ LAL | HOME | 55.2% | 79.8% | +24.5% | 79.8% | +24.5% | yes | **win** | no curated outs |
| 11-05 | MIN @ HOU | AWAY | 70.2% | 64.1% | −6.1% | 64.1% | −6.1% | yes | **win** | — |
| 11-08 | LAL @ DET | AWAY | 70.2% | 66.5% | −3.7% | 66.5% | −3.7% | yes | **win** | — |
| 11-10 | NOP @ GSW | AWAY | 81.0% | 72.8% | **−8.2%** | 79.1% | **−1.9%** | **no** | **loss** | NOP stars out → edge drops under 3% |
| 11-14 | GSW @ SAS | HOME | 84.1% | 89.1% | +5.0% | 90.2% | +6.0% | yes | **win** | Curry out (away) widens SAS lean |
| 11-19 | ATL @ OKC | HOME | 69.5% | 83.4% | **+13.9%** | 79.4% | **+10.0%** | yes | **loss** | OKC: Holmgren+J.Williams+Wallace (−45) |
| 11-19 | GSW @ DAL | AWAY | 63.8% | 52.2% | **−11.6%** | 60.0% | **−3.8%** | yes | **loss** | GSW: Curry+Butler+… (−55) shrinks away edge |
| 11-19 | DET @ NOP | AWAY | 37.1% | 26.5% | −10.6% | 22.3% | −14.9% | yes | **win** | NOP outs deepen away lean |

---

## Impact summary

| Metric | Before (raw) | After (injury-adj) |
|---|---|---|
| Signals that would alert (|edge|≥3%) | 9/9 | **8/9** |
| Losing signals still alerted | 4 | **3** (NOP@GSW suppressed) |
| Group C (|edge|>10%) count | 5 | **3** (GSW@DAL shrinks to 3.8%; OKC still 10%) |
| Paper W-L on remaining alerts | 5–4 | **5–3** on the 8 (NOP@GSW loss avoided) |

### Key wins of the layer
- **NOP @ GSW (11-10):** away edge −8.2% → −1.9% → **no Telegram**. That paper signal was a loss; filter would have saved it.
- **GSW @ DAL (11-19):** away edge −11.6% → −3.8%. Still alerts, but no longer a “monster” gap.
- **ATL @ OKC (11-19):** +13.9% → +10.0%. Reduced but still above 3% and still a loss — residual gap from incomplete depth modeling.

### Limitations (honest)
- Backtest injuries are **hand-labeled** for the 9 dates; live uses ESPN current board only.
- Questionable / Day-To-Day ignored in v1 (too noisy).
- No minutes-based continuous severity — only Tier-1/2 discrete hits.
- Both teams injured (LAC vs TOR) can leave a large residual edge.
- n=9 is not statistical proof; this is a **sanity filter**, not a proven alpha source.

---

## Live wiring

- `scripts/injury_adjuster.py` — ESPN fetch + cache + penalty math.
- `config/star_tiers.json` — editable Tier-1 / Tier-2 lists.
- `scripts/live_collector.py` — `load_model_prob()` calls injury layer; **fallback to raw Elo** if ESPN/cache fails.
- Telegram messages now **Arabic**, with automatic suspect tag when |edge| ≥ 15% after adjustment.

---

## Recommendation

**Activate live injury-aware Path A.**  
Keep alert threshold at ≥ 3%. Continue logging all rows; treat residual |edge| > 15% as `suspect_calibration` in human review. Do **not** retrain XGB/LSTM from this layer alone.

Next data-quality steps (not this PR): expand star_tiers from actual minutes leaders; optional half-penalty for Questionable; archive daily injury JSON for true historical backtests.
