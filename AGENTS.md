# AGENTS.md — guide for AI agents & contributors

This file tells an automated agent (or a new human contributor) how to work in this
repo safely. Keep changes consistent with the contracts below.

## What this project is

SynthLaunch estimates the causal impact of a launch that can't be A/B tested, using
the Synthetic Control Method (SCM), a Difference-in-Differences (DiD) baseline, and
placebo-permutation inference, with an optional Claude-written product memo. A FastAPI
process serves the JSON API **and** the built React frontend, so it runs from one URL.

Frontend stack: **Vite + React + TypeScript + Tailwind v4 + shadcn/ui** (Plotly for
charts). Note shadcn here uses the **base-ui** primitives (`@base-ui/react`), whose
props differ from Radix (e.g. Accordion uses `multiple` not `type`/`collapsible`;
Tooltip provider uses `delay`; Select `onValueChange` yields `string | null`).

## Setup & run

```bash
./run.sh                                   # venv + deps + build frontend + server :8000
./.venv/bin/python -m pytest tests/ -q     # backend test suite (~1–2 min)
./.venv/bin/python scripts/build_data.py   # rebuild bundled datasets
npm --prefix frontend run build            # rebuild the UI after frontend edits
npm --prefix frontend run dev              # UI hot-reload (proxies /api to :8000)
```

Use the existing `.venv`; don't introduce a different Python package manager.
Python 3.11+, Node 18+. The backend serves `frontend/dist` — **rebuild after UI edits**.

## Map of the code

| File | Responsibility | Change it when… |
|------|----------------|-----------------|
| `backend/synthlaunch/scm.py` | SCM fit, DiD, placebo, confidence | changing the statistics |
| `backend/synthlaunch/validation.py` | data-contract checks | changing input rules |
| `backend/synthlaunch/datasets.py` | bundled + uploaded registry | adding a dataset |
| `backend/synthlaunch/memo.py` | AI memo + offline fallback | changing memo behaviour |
| `backend/app.py` | FastAPI endpoints (incl. `/api/analyze`), serves `frontend/dist` | adding/altering an endpoint |
| `frontend/src/App.tsx` | dashboard, charts, per-chart explainers | UI changes |
| `frontend/src/lib/api.ts` | typed API client + response types | API contract changes |
| `frontend/src/components/` | `Chart.tsx`, `HowToRead.tsx`, `ui/` (shadcn) | reusable UI |
| `scripts/build_data.py` | regenerate demo CSVs (stdlib only) | dataset generation |
| `tests/` | pytest | always add/adjust tests with code changes |

## The data contract (do not break)

Tidy CSV, one row per (unit, date): **`date`** (ISO-8601), **`unit_id`** (string),
**`metric`** (numeric). Internally the panel is pivoted to *wide* form
(`scm.pivot_panel`) — date index, one column per unit. ISO date strings are compared
lexicographically, so the pre/post split is `date < intervention_date`. If you add a
column or alternate header support, update `validation.normalise` and the contract in
both `README.md` and `idea.md`.

## Statistical guardrails — preserve these invariants

1. **SCM weights** must satisfy `ΣW = 1` and `W ≥ 0` (simplex). Fit on the
   **pre-period only**. Keep the multi-restart + fixed-seed pattern so results stay
   **reproducible** (`tests/test_scm.py::test_placebo_pvalue_reproducible`).
2. **Intervention date is an a-priori input**, never auto-tuned to maximise the effect.
   The UI "exploration mode" must keep its warning and keep **inference disabled**.
3. **Inference** is the RMSPE-ratio placebo test; the empirical p-value is the treated
   unit's rank among all units. Don't silently swap in a parametric p-value.
4. **Confidence** is computed in Python (`scm.compute_confidence`) from p-value, donor
   count, and pre-period length. The **memo must respect it** — `memo.py` instructs the
   model never to invent ROI or upgrade a weak result. Keep both halves in sync.
5. The MVP is **outcome-only SCM** (no predictor covariates) — a documented
   approximation. If you add predictors, keep outcome-only working and update the docs
   and the Prop 99 expectation in the tests.

## How to add a bundled dataset

1. Drop a tidy CSV in `backend/data/` (or generate it in `scripts/build_data.py`).
2. Add an entry to `datasets.BUNDLED` with `title`, `treated`, `intervention`,
   `metric_label`, `description` (and `true_att` if synthetic).
3. Add it to `tests/test_validation.py::test_bundled_datasets_pass`.

## Conventions

- Standard library + the existing deps only; discuss before adding a dependency.
- Endpoints return plain JSON; validation failures are HTTP **422** with a structured
  body (`{stage, ok, errors, warnings, info}`). Keep that shape.
- The frontend is intentionally a single dependency-free HTML file. Don't add a
  bundler/framework without a clear reason.
- Always run `pytest` before declaring a change done; add a test for new behaviour.

## Safe-change checklist

- [ ] `pytest tests/ -q` passes.
- [ ] After UI edits, `npm --prefix frontend run build` succeeds (no TS errors).
- [ ] Server boots (`./run.sh`) and `/`, `/api/analyze`, `/api/memo` respond.
- [ ] Statistical invariants above still hold.
- [ ] README/idea.md updated if the contract or methodology changed.
