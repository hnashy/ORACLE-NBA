# Cluster Analysis — Nov 19, 2026 (3 large edges) + Cumulative Ledger

> Structural audit only. No ROI / PnL. Paper signals at T-10m (|edge| ≥ 3%).

Generated: 2026-11-19 (analysis pass after finals).

---

## 1. Nov 19 cluster — final outcomes

| Match | Signal | Elo p(H) | Mkt p(H) | Edge | Final | Paper |
|---|---|---:|---:|---:|---|---|
| GSW @ **DAL** | **AWAY** (GSW) | 52.2% | 63.8% | **−11.6%** | DAL **116–94** GSW | **loss** |
| DET @ **NOP** | **AWAY** (DET) | 26.5% | 37.1% | **−10.6%** | DET **122–109** NOP | **win** |
| ATL @ **OKC** | **HOME** (OKC) | 83.4% | 69.5% | **+13.9%** | ATL **117–112** OKC | **loss** |

**Cluster score: 1 win / 2 losses.**  
Large-edge night did **not** deliver a clean paper streak.

### Price movement (T-6h → T-10m) for the cluster

| Match | p(H) T-6h | p(H) T-10m | Δ p(H) | Δ Total | Conf |
|---|---:|---:|---:|---:|---|
| ATL @ OKC | 68.3% | 69.5% | +1.2% | +0.1 | stable |
| GSW @ DAL | 63.2% | 63.8% | +0.6% | −1.6 | moderate |
| DET @ NOP | 34.3% | 37.1% | +2.8% | −3.5 | volatile |

No dramatic late swing *toward* the model. Market stayed firm (or moved slightly against the model side on DET/NOP total).

---

## 2. Why three >10% edges on one night? (root cause)

Not All-Star break (early regular season, mid-November). Dominant driver: **injury / roster gaps that static Elo does not see**, same class as TOR@LAC (Nov 3).

### GSW @ DAL (−11.6% AWAY signal → loss)
- **Warriors:** Stephen Curry (right oblique tear), Jimmy Butler (ACL), Moses Moody, Kristaps Porziņģis, Brandon Williams, Draymond Green listed out around this stretch. Road trip already poor.
- **Mavericks:** Some depth outs (Lively long-term) but core available; Cooper Flagg dominated the win.
- Elo still treated GSW near parity (52% home for DAL). Market correctly priced a depleted GSW road side (~64% DAL). **Market right.**

### DET @ NOP (−10.6% AWAY signal → win)
- **Pelicans:** Heavy outs in the period (Trey Murphy III, Dejounte Murray, Trendon Watford, Mathurin, McGowens often listed).
- Elo p(H)=26.5% already very low; market 37% — still an away lean for DET. DET won 122–109. **Direction correct; large magnitude still driven by availability mismatch.**

### ATL @ OKC (+13.9% HOME signal → loss)
- **Thunder:** Chet Holmgren, Jalen Williams, Cason Wallace long-term outs; Caruso day-to-day. Elo still assigned OKC ~83% home vs market ~70%.
- Hawks won 117–112. **Elo over-trusted historical OKC strength without current availability.** Same pattern as Clippers in week 1.

**Cluster diagnosis:** simultaneous multi-team injury noise, not a sudden “model upgrade.” Static Elo + no injury layer → sporadic large |edge| whenever public availability diverges from historical ratings.

---

## 3. Cumulative paper ledger (all T-10m signals |edge| ≥ 3%)

| # | Date (tip UTC day) | Match | Side | Edge | Result | Paper |
|---:|---|---|---|---:|---|---|
| 1 | 2026-11-03 | TOR @ LAC | HOME | +33.2% | TOR 125–118 | **loss** |
| 2 | 2026-11-03 | MIA @ LAL | HOME | +24.5% | LAL 138–117 | **win** |
| 3 | 2026-11-05 | MIN @ HOU | AWAY | −6.1% | MIN 117–107 | **win** |
| 4 | 2026-11-08 | LAL @ DET | AWAY | −3.7% | LAL 121–116 | **win** |
| 5 | 2026-11-10 | NOP @ GSW | AWAY | −8.2% | GSW 138–87 | **loss** |
| 6 | 2026-11-14 | GSW @ SAS | HOME | +5.0% | SAS 123–85 | **win** |
| 7 | 2026-11-19 | ATL @ OKC | HOME | +13.9% | ATL 117–112 | **loss** |
| 8 | 2026-11-19 | GSW @ DAL | AWAY | −11.6% | DAL 116–94 | **loss** |
| 9 | 2026-11-19 | DET @ NOP | AWAY | −10.6% | DET 122–109 | **win** |

**Overall: 5 wins / 4 losses (9 signals).**  
Descriptive only — n is still tiny; no claim of edge.

### By |edge| bucket

| Bucket | n | Wins | Losses | Hit rate (paper) |
|---|---:|---:|---:|---:|
| **A** \|edge\| < 5% | 1 | 1 | 0 | 1/1 |
| **B** 5–10% | 3 | 2 | 1 | 2/3 |
| **C** \|edge\| > 10% | 5 | 2 | 3 | **2/5** |

**Finding:** The largest gaps (Group C) are **not** more reliable so far. They concentrate on injury-skewed matchups where Elo is least calibrated. Moderate edges (B) look cleaner on this sample, but n=3 is not evidence.

---

## 4. Go / No-Go on alert threshold

| Option | Rationale | Recommendation |
|---|---|---|
| Keep ≥ 3% | Maximizes sample for documentation phase | **Preferred for now** while Path A is still a *data + timing* scaffold |
| Raise to ≥ 5% | Drops noise; Group C alone is 2/5 and injury-driven | Reasonable *later* once injury flag exists |
| Lower to ≥ 1.5% | Faster n, lower average quality | **No** — dilutes already noisy prior |

**Decision: keep ≥ 3% for Telegram/paper logging.**  
Do **not** treat Group C as “high confidence.” Optional ops rule (documentation only): tag `|edge| > 15%` as `suspect_calibration` in human review (same class as TOR@LAC case study).

**Do not** retrain Elo/XGB from n=9. Priority remains:
1. Injury / availability input layer (Path B scope).
2. Full window capture (T-1h still often missing).
3. Accumulate clean T-10m rows with outcomes.

---

## 5. Ops notes

- Credits remaining ~340 (from 2026-11-19 review) — 5-min cadence still viable but watch burn.
- Zero games with complete T-6h/T-1h/T-10m triple in latest review — movement analysis remains partial.
- Cluster is consistent with prior diagnosis: **large edges ≈ missing injury context**, not sudden alpha.

---
Sources: `data/live_collection/master_log.csv`, `reports/live_reviews/review_2026-11-19.md` (+ earlier reviews); public finals (NBA.com / AP recaps); injury reports (team / ESPN-style lists) 2026-11-18–19.
