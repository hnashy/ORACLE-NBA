# Case Study: TOR @ LAC — 2026-11-02 (tip 03:10 UTC 2026-11-03)

> Structural diagnosis only. No Elo/XGB code change. Sample n=1 within first live night.

## 1. What the live system recorded

| Snapshot | Elo p(Home=LAC) | Market de-vig p(H) | Edge | ML home (sample) | Total |
|---|---:|---:|---:|---|---:|
| T-6h | 66.8% | 38.3% | +28.6% | ~+150 | 219.5 |
| T-10m | 66.8% | 33.6% | **+33.2%** | **+190** | 219.5–220 |
| Final | — | — | — | — | **TOR 125 – LAC 118** |

Paper signal at T-10m: **HOME** → outcome **loss** (away won).

Market moved *further against* Clippers into the close (38.3% → 33.6%). Confidence on totals: `stable` (Δ total ≈ +0.4).

## 2. Elo inputs (snapshot `data/processed/elo_ratings.json`)

| Team | Elo | Rank in snapshot |
|---|---:|---|
| Los Angeles Clippers | **1532.6** | mid-pack (~15th of 30) |
| Toronto Raptors | **1511.0** | slightly below Clippers |

Params used by collector: `K=20`, **HCA=+100**, default 1500.

Implied home win probability with HCA=+100 is ≈ **66.8%**. **No arithmetic bug.**

Source: cumulative walk over `games_clean.csv` (~2497 rows). Snapshot is **not** injury-adjusted and **not** limited to 2026-27 form.

## 3. Match context the market priced and Elo ignored

### Form
- Clippers entered **1–5**, on a **5-game losing streak** (1–6 after this loss).
- Raptors **3–3**.

### Injuries (public reports, 2026-11-02)
**Clippers OUT (heavy):** Bradley Beal (knee), Brandon Ingram (heel/Achilles), Rui Hachimura (quad), Derrick Jones Jr. (knee), Jordan Miller (rotator cuff surgery), Yanic Konan Niederhauser (Lisfranc).

Skeleton rotation (Garland / Dunn / Lopez + fringe). Kobe Sanders scored career-high 26 in the loss.

**Raptors:** Kawhi Leonard OUT (knee, multi-week); B2B after loss at Lakers; Barnes/Poeltl were questionable pre-tip. Market still roughly TOR −5.5.

### Rest
Both sides B2B. Path A live collector uses **static Elo only** — no rest/B2B feature.

## 4. Why PHX @ GSW was “normal” the same night

| Match | Elo p(H) | Mkt p(H) | \|Edge\| | Result |
|---|---:|---:|---:|---|
| PHX @ GSW | 55.1% | 55.5% | **0.3%** | GSW 116–113 |
| TOR @ LAC | 66.8% | 33.6% | **33.2%** | TOR 125–118 |
| MIA @ LAL | 79.8% | 55.2% | 24.5% | LAL 138–117 |

GSW/PHX: ratings and market agreed → no alert.  
LAC: ratings treated a **decimated, skidding roster** as a mid-tier home favorite. Market had already priced injuries + form.

## 5. Root cause class (data inputs, not formula)

| Hypothesis | Supported? |
|---|---|
| Arithmetic / alias bug | No |
| Stale / non-injury-aware Elo snapshot | **Yes — primary** |
| Missing rest/B2B in Path A | Yes — secondary |
| True market inefficiency | No — result agrees with market + injury report |

This is the failure mode Path B (injury features) was scoped to address. Path A is a timing + logging scaffold with a crude prior.

## 6. Suggested *input* improvements (no model retrain yet)

1. **Injury flag (read-only):** if many starters out, tag `injury_contaminated` and optionally suppress Telegram (still log).
2. **Short-form blend** with last-N 2026-27 games once sample grows — not a full retrain.
3. **Magnitude gate:** treat \|edge\| > ~15–20% as *suspect calibration* until injury/form inputs exist.
4. Keep collecting full windows so future models can score on true close timing.

## 7. Decision log

- **Do not** patch Elo from n=1–3 live games.
- **Do** treat TOR@LAC as a positive control: system detected disagreement; disagreement explained by missing injury/form inputs, not a collector coding error.

---
Sources: master_log, elo_ratings.json, review_2026-11-03.md; public injury reports (AP / team PR) 2026-11-02.
