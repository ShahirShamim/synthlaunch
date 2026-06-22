# 🚀 SynthLaunch

**Causal inference for launches you can't A/B test.** Upload a panel of a metric
over time across markets/cohorts, pick the treated unit and the launch date, and
SynthLaunch builds a **synthetic control** — a weighted blend of untreated "donor"
units that tracks the treated unit *before* the launch — then measures the gap
*after* the launch as the causal effect. It ships with **Synthetic Control**,
a **Difference-in-Differences** baseline, **placebo permutation inference**, and an
optional **AI product memo**.

The UI is a **React + TypeScript + Tailwind v4 + shadcn/ui** app (charts via Plotly);
FastAPI serves the built frontend so the whole thing still runs from one process and
one URL. The AI memo works **offline** (deterministic template) and upgrades to Claude
prose when you add an API key. Every chart has a plain-language **“How to read this”**
explainer, so it's usable by a non-technical audience.

---

## Quickstart

Prereqs: **Python 3.11+** and **Node 18+** (for the one-time frontend build).

```bash
./run.sh
# → open http://localhost:8000
```

First run creates the Python venv, installs deps, **builds the frontend**, and copies
`.env.example` → `.env`. Subsequent runs skip the build (delete `frontend/dist` to rebuild).

Manual equivalent:

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
npm --prefix frontend install && npm --prefix frontend run build
./.venv/bin/python -m uvicorn app:app --app-dir backend --port 8000
```

Then pick **California Prop 99 (real)** in the sidebar and hit **Run analysis**.

### Frontend dev mode (hot reload)

```bash
./.venv/bin/python -m uvicorn app:app --app-dir backend --port 8000   # API
npm --prefix frontend run dev                                          # → http://localhost:5173
```

The Vite dev server proxies `/api` to port 8000.

---

## What you get

| Panel | What it shows |
|-------|----------------|
| Treated vs Synthetic vs Naive average | why the weighted synthetic beats a plain average of controls |
| Cumulative lift | net effect (treated − synthetic) accumulated after the launch |
| Donor weights donut | which donor units compose the synthetic control |
| Placebo spaghetti + p-value | each unit treated as a fake "treated" → empirical significance |
| Validity gates | ATT, % lift, empirical p, pre-fit MSPE, confidence label |
| AI Causal Memo | plain-language summary that **respects** the confidence label |

## Bundled datasets

- **California Prop 99 (REAL)** — Abadie, Diamond & Hainmueller (2010). 39 US states,
  1970–2000, per-capita cigarette sales; California's 1989 tobacco program is *the*
  canonical synthetic-control case. Outcome-only SCM here recovers ATT ≈ **−19 packs**
  (−24%), empirical **p ≈ 0.08** (California in the top ~8% of placebos).
- **Brexit — cost to UK GDP (REAL, UK)** — World Bank GDP per capita (rebased to an
  index so growth paths are comparable), UK vs 21 advanced economies, 1995–2019,
  intervention 2016. The UK tracks its synthetic twin closely until 2016, then drifts
  **below** it. On annual data this shortfall is **visible but not strongly significant**
  (the famous ~2% figures used quarterly data) — a deliberately honest example that
  teaches *not over-claiming*.
- **B2B marketplace pricing (SYNTHETIC)** — generated panel with a **known injected
  −8% effect** (true ATT ≈ −9.54). The engine recovers ATT ≈ **−9.98** and puts the
  weight back on the true donors — a built-in ground-truth check.

Rebuild them any time: `./.venv/bin/python scripts/build_data.py`.

## Bring your own data

Upload a **tidy CSV** (drag it into the sidebar). Three columns:

```csv
date,unit_id,metric
2020-01-01,London,1043.2
2020-01-01,Berlin,980.5
...
```

- `date` — ISO-8601, consistent frequency. `unit_id` — string. `metric` — numeric.
- Must be a **balanced panel** (every unit present at every date).
- Need ≥ 1 treated + ≥ 2 donors (≥ 5 donors recommended for a usable p-value).
- The API also accepts a `columns` map (e.g. `{"date":"week","unit_id":"city","metric":"rev"}`)
  so you don't have to rename your headers.

The app validates on upload and tells you the exact offending cell if anything is off.

## Bring your own API key

The AI memo is optional and pluggable:

- **No key** → a deterministic memo is built from the numbers (fully offline).
- **With a key** → Claude writes the prose via a forced structured tool call.

Provide the key either in the UI's *AI memo* box, or in `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
SYNTHLAUNCH_MODEL=claude-haiku-4-5-20251001   # or claude-opus-4-8 for best quality
```

Either way **the numbers and the confidence label are computed in Python**; the model
only writes prose and is instructed never to invent ROI or upgrade a weak result.

---

## Methodology & guardrails

- **Weights** solve `min ‖y_pre − X_pre·W‖²` s.t. `ΣW=1, W≥0` (SciPy SLSQP, multiple
  seeded restarts → reproducible).
- **The intervention date is a locked input.** "Exploration mode" lets you move it for
  sensitivity checking, but it shows a warning and **disables inference** — moving the
  date to maximise the effect is p-hacking, not an estimate.
- **Inference** is the RMSPE-ratio placebo test: post/pre MSPE ratio per unit; empirical
  `p` = the treated unit's rank among all units. A pruned variant drops placebos with
  poor pre-fit. An in-time placebo backdates the launch and should show ≈ no effect.
- **Confidence** (`high/medium/low/insufficient`) is gated on p-value, donor count, and
  pre-period length — and < 5 donors is flagged as *insufficient* regardless of p.
- **Outcome-only SCM** (no predictor covariates) — a documented approximation; see
  `idea.md` §5. Predictor matching is the main fast-follow.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET  /api/datasets` | list bundled + uploaded datasets |
| `GET  /api/datasets/{id}` | dataset records + validation report |
| `POST /api/datasets/upload` | upload + validate a CSV (multipart) |
| `POST /api/validate` | panel + intervention validity report |
| `POST /api/fit` | SCM weights, synthetic series, ATT, MSPE + DiD baseline |
| `POST /api/placebo` | in-space + in-time placebo paths and p-value |
| `POST /api/analyze` | **fit + DiD + placebo + confidence in one call** (what the UI uses) |
| `POST /api/memo` | confidence label + AI/template product memo |

## Project layout

```
backend/
  app.py                 FastAPI app (API + serves built frontend)
  synthlaunch/
    scm.py               SCM, DiD, placebo inference, confidence  ← stats core
    validation.py        data-contract checks
    datasets.py          bundled + uploaded dataset registry
    memo.py              AI memo (Claude) with offline fallback
  data/*.csv             bundled tidy panels
frontend/                React + TS + Tailwind v4 + shadcn/ui (Vite); Plotly charts
  src/App.tsx            dashboard + per-chart explainers
  src/lib/api.ts         typed API client
  src/components/        Chart.tsx, HowToRead.tsx, ui/ (shadcn)
  dist/                  built output served by FastAPI (gitignored)
scripts/build_data.py    rebuild bundled datasets (stdlib only)
tests/                   pytest: ground-truth recovery, reproducibility, contract
idea.md                  product/engineering spec
AGENTS.md                guide for AI agents / contributors
```

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q
```

Covers ground-truth ATT recovery, simplex constraints, p-value reproducibility,
the Prop 99 result, in-time placebo, and the validation contract.

## Troubleshooting

- **Port in use** → `PORT=8001 ./run.sh`.
- **Memo says "template (API error: …)"** → bad/missing key or no network; the demo
  still works, it just used the offline memo.
- **Upload rejected** → read the error; it names the offending `(unit, date)` cell.
