# ORACLE-NBA Data Registry

Last updated: 2026-11-03 (UTC)

## Live Path A — status

| Item | Value |
|------|--------|
| **Status** | **Active live collection** |
| **Collector** | `scripts/live_collector.py` |
| **Schedule** | `*/5 * * * *` (temporary 1-week denser cadence to secure T-1h; was `*/15`) |
| **Windows** | T-6h, T-1h, T-10m (±12 min) |
| **Coverage (first night)** | T-6h ✓ · T-10m ✓ · **T-1h pending fix** (0/3 games 2026-11-03) |
| **Log** | `data/live_collection/master_log.csv` (committed by Actions) |
| **Alerts** | Telegram paper-only if \|edge\| ≥ 3% at **T-10m only** |
| **Model prior** | Static Elo snapshot `data/processed/elo_ratings.json` (HCA=+100, K=20) |
| **Post-match** | `scripts/post_match_review.py` → `reports/live_reviews/review_YYYY-MM-DD.md` (08:00 UTC + manual) |

## Initial findings (n small — descriptive only)

- Model–market variance can be extreme when Elo lacks injury/form context.
- Example: TOR @ LAC 2026-11-02 → Elo 66.8% home vs market 33.6%; market correct (TOR 125–118). See `reports/case_studies/case_study_tor_lac_analysis.md`.
- Same night PHX @ GSW: \|edge\| ≈ 0.3% (aligned); no alert.
- No ROI/PnL computed. Paper W/L is documentation only.

## Hard constraints (current phase)

- No paid API upgrades without explicit approval.
- No Elo / XGB / LSTM parameter changes from live n≪30.
- Discovery + timing integrity first; edge claims later.

## Credit watch

- Free Odds API tier. Monitor `credits_remaining` in master_log.
- If remaining < ~450 within ~2 days under 5-min cadence → revert schedule to `*/15` and consider targeted retry near known tips.
