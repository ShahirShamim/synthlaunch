# 🚀 SynthLaunch — Causal Inference Build Spec

> Web app that estimates the causal impact of a launch when A/B testing is impossible, using the Synthetic Control Method (SCM) and Difference-in-Differences (DiD). This document is the **engineering build spec** for the MVP.

---

## 1. Problem & Job-to-be-Done

Product teams often ship changes that **cannot be cleanly randomized**:

- Geo rollouts (new pricing in one country, a physical store change).
- B2B / marketplace changes where **network effects** break randomization.
- Platform-wide policy changes (a new paywall, a fee) applied to a whole cohort.

When you can't A/B test, the question "did it work, and by how much?" is usually answered with a gut-feel before/after chart that ignores the trend the metric would have had anyway.

**Job-to-be-done:** *"Give me a defensible estimate of what would have happened without the launch, so I can state the causal impact with a credible confidence level — without writing econometrics code."*

**Solution:** Build a **synthetic counterfactual** — a weighted blend of untreated "donor" units (e.g. Berlin, Madrid, Amsterdam) chosen to track the treated unit (e.g. London) in the **pre-launch** period. The post-launch gap between treated and synthetic is the estimated causal effect.

---

## 2. Target User & Core Assumption

- **Primary user:** a growth PM or growth/analytics engineer who has access to a time-series export and wants a credible causal read without a data-science ticket.
- **Secondary user:** a data scientist who wants a fast first-pass / visual sanity check before a rigorous model.

**Riskiest assumption (validate early):** the user can supply a **balanced panel** — the same metric, for multiple units, over many periods, with **enough pre-launch history** (rule of thumb: pre-period length ≥ ~3× the number of donor units, and ≥ 8 periods minimum). If users don't have this shape of data, the product has no input. Treat this as a discovery risk, not a given — see §11.

---

## 3. Scope

**In MVP**

- Single treated unit per analysis.
- Outcome-only SCM (donor weights fit on the lagged outcome itself — see §5 note).
- DiD as a baseline comparator.
- Placebo-based inference (in-space + in-time) with an empirical p-value.
- AI "Causal Product Memo" with guardrails.
- 3 bundled demo datasets so the app is usable with zero upload.

**Not in MVP** (explicitly cut)

- Multiple or **staggered** treated units / adoption dates.
- Predictor covariates beyond outcome lags (classic Abadie SCM uses auxiliary predictors; deferred).
- Accounts, auth, persistence — analysis is stateless / in-session.
- **Real-time auto-refit on every slider tick** (perf + p-hacking risk — see §5).
- Multi-metric joint analysis (one metric per run).

---

## 4. Data Contract  *(the centerpiece — `/validate` enforces this)*

**Format:** tidy / long CSV, one row per (unit, date).

| column    | type            | rule                                  |
|-----------|-----------------|---------------------------------------|
| `date`    | ISO-8601 string | parseable; consistent frequency       |
| `unit_id` | string          | identifies market / cohort / store    |
| `metric`  | numeric         | non-null, finite                      |

**Validation rules** (each is a testable `/validate` check, and a §9 acceptance criterion):

1. **Balanced panel** — every `unit_id` has a row at every `date`. Reject on a missing cell and **name the offending (unit, date)**.
2. **No duplicates** — `(unit_id, date)` is unique. Reject and name the duplicate key.
3. **Metric is numeric & non-null** — reject and name the first bad cell.
4. **Cohort size** — ≥ 1 treated unit and ≥ 2 donor units (≥ 5 donors recommended for a usable p-value — see §5).
5. **Pre-period length** — ≥ 8 pre-intervention periods; warn below the ~3×donors rule of thumb.
6. **Intervention date** — falls strictly inside the date range, leaving pre- and post-windows, plus a configurable **no-anticipation buffer** (periods just before the date that are excluded from the fit).

`/validate` returns a structured report: `ok | warnings[] | errors[]`, each with a machine-readable code and the offending key.

---

## 5. Methodology & Guardrails  *(the trust core)*

**SCM weight fit.** Find weight vector `W` over donor units minimizing pre-intervention **MSPE** (mean squared prediction error) between treated and synthetic, subject to `Σ Wᵢ = 1` and `Wᵢ ≥ 0`. Solver: `scipy.optimize.minimize` with **SLSQP**. Convex; use a fixed seed / fixed start for reproducibility.

> **Note (honesty about the method):** MVP fits weights on the **outcome series itself** (and its pre-period lags), not on separate predictor covariates as in canonical Abadie SCM. This is a defensible approximation for a first-pass tool; flag it in the memo and in §11.

**⚠️ Intervention date is a LOCKED, a-priori input — not a knob to maximize the effect.**
Dragging a slider to find the treatment date that produces the biggest effect is **p-hacking** and invalidates the inference. Therefore:

- The default flow requires the user to **enter and lock** the intervention date (the real launch date) **before** the post-period result is shown.
- The interactive slider exists only inside a clearly labeled **"Exploration mode"** banner ("for sensitivity checking only — not a valid effect estimate"), and never auto-refits silently into the reported result.

**Validity gates** surfaced to the user before they trust a number:

- **Pre-fit quality** — pre-period MSPE, and pre-MSPE relative to the donor distribution. Poor pre-fit ⇒ red flag.
- **Min pre-periods** — from §4.5.
- **Donor-pool contamination** — no donor unit may itself be treated/affected by the intervention; surface a checklist.
- **No-anticipation window** — exclude the buffer periods from the fit.

**Inference (empirical p-value).**

- **In-space placebo:** re-run the SCM treating **each donor** as if it were the treated unit. Compute each unit's **post/pre MSPE ratio**.
- **In-time placebo:** re-run with a **fake** earlier intervention date on the real treated unit; the effect should vanish.
- **p-value** = rank of the treated unit's post/pre MSPE ratio among all placebos (e.g. treated is largest of 20 ⇒ p ≈ 1/20 = 0.05). State clearly that **with < ~5 donors the p-value is not meaningful**.

**DiD baseline.** Report a two-way fixed-effects DiD estimate as a comparator, with an explicit **parallel-trends** caveat (DiD assumes treated and control trended together pre-launch; show the pre-trend so the user can judge it).

---

## 6. API Contracts (FastAPI)

All endpoints stateless; panel passed in or referenced by an in-session id.

| Endpoint        | Request (key fields)                                                       | Response (key fields)                                                                 |
|-----------------|----------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| `POST /validate`| raw CSV / parsed rows                                                       | `{ ok, warnings[], errors[], inferred: {units[], date_range, frequency} }`           |
| `POST /fit`     | `{ panel, treated_unit, metric, intervention_date, anticipation_buffer }`  | `{ weights[{unit, w}], synthetic_series[], att, pct_lift, pre_mspe, post_mspe }`      |
| `POST /placebo` | `{ panel, treated_unit, metric, intervention_date, mode: in_space|in_time }`| `{ placebo_paths[], treated_path, p_value, n_donors, mspe_ratios[] }`                 |
| `POST /memo`    | `{ fit_result, placebo_result, validity_gates, context }`                  | `{ memo_markdown, confidence: high|medium|low|insufficient, assumptions[] }`          |

`/placebo` runs N−1 optimizations; parallelize across donors. Seed fixed for reproducibility.

---

## 7. AI Causal Copilot — Guardrails

LLM turns the numbers into a "Causal Product Memo." Because it is generating **causal claims**, it is constrained:

- **Structured output** via tool-use / JSON schema (ATT, % lift, p-value, confidence, assumptions, caveats) — no free-form numeric invention.
- **Refuse or downgrade** when pre-fit MSPE is poor, pre-periods are too few, or donors < threshold → return `confidence: "low" | "insufficient"` and say *why*, rather than asserting a clean result.
- **No fabricated ROI** — monetary impact only when the user supplies the unit economics; otherwise report effect in metric units.
- Always lists the assumptions in plain language (locked date, no anticipation, donor validity, parallel-trends for DiD).

> **Model recommendation:** the original draft named the Gemini API. Recommend **Claude** instead — **Opus 4.8** (`claude-opus-4-8`) for best memo quality, or **Haiku 4.5** (`claude-haiku-4-5-20251001`) for cost — using the Anthropic SDK with **tool use** for the structured schema. (Open to the team's preference; swap is isolated to the `/memo` client.)

---

## 8. Frontend

Stack (as built): **React + TypeScript + Tailwind CSS v4 + shadcn/ui** (Vite build), charts via **Plotly**. Dark UI. FastAPI serves the built `frontend/dist`. Every chart carries a plain-language **"How to read this"** explainer for a non-technical audience.

Charts:

1. **Treated vs Synthetic vs Naive-Average** time series — includes the simple average control to show *why* the synthetic fit is better.
2. **Cumulative Lift** area chart — net value accrued post-launch.
3. **Donor-Weight Donut** — which donors compose the synthetic control.
4. **Placebo Spaghetti Plot** — all placebo paths in grey, treated path highlighted.

UI rule: the **Exploration-mode slider** (§5) is visually distinct and gated behind a warning banner; the reported result uses the locked date only.

---

## 9. Phased Build & Acceptance Criteria

Each item is written as a **testable** criterion.

**Phase 1 — Data Sandbox**
- Drag-and-drop CSV parser; AC: a 3-column tidy CSV loads and previews inferred units + date range.
- `/validate`; AC: rejects a panel with a missing `(unit, date)` cell and **names that cell**; rejects a duplicate key and names it; warns when pre-periods < threshold.
- Bundled demo datasets selectable; AC: all 3 load and **pass `/validate`** with zero errors.

**Phase 2 — Inference Engine (Python)**
- SLSQP SCM fit; AC: on a fixture where the true synthetic is known, recovered weights match within tolerance and satisfy `ΣW=1, W≥0`.
- DiD baseline; AC: returns an estimate + pre-trend series for the same fixture.
- Placebo engine; AC: on a **fixed seed**, the empirical p-value is reproducible exactly run-to-run; in-time placebo on a no-effect period yields a non-significant result.

**Phase 3 — Visualizations (React)**
- The 4 charts above render from `/fit` + `/placebo` payloads; AC: donut weights sum to 100%; spaghetti plot highlights the treated path; exploration slider shows the warning banner and never overwrites the locked-date result.

**Phase 4 — AI Memo**
- `/memo` client + schema; AC: with good pre-fit returns `confidence: high` and the correct ATT/% lift; with **degraded pre-fit** (forced high pre-MSPE) returns `confidence: insufficient` and refuses a clean claim; never emits monetary ROI unless unit economics were supplied.

---

## 10. Bundled Demo Datasets

Must be **valid balanced panels** that pass `/validate`:

1. **B2B Marketplace Pricing** — 2% transaction fee launched in **London**; donors: Berlin, Amsterdam, Madrid (+ more for a usable p-value).
2. **SaaS Paywall Restructuring** — stricter paywall on **iOS**; donors: Android, Web cohorts.
3. **E-Commerce Free-Shipping Threshold** — free shipping at £50 in the **UK**; donors: Germany, France, Italy (+ more).

Each ships with a known/plausible "true" effect so demos visibly produce a real result.

---

## 11. Risks & Open Questions

- **Data availability (riskiest):** do target users actually have balanced panels with enough pre-history? Mitigation: lead with demo datasets; ship a clear template + `/validate` errors. *Validate before building Phase 2 heavily.*
- **Misuse of the slider:** non-experts may treat exploration mode as a result. Mitigation: lock-by-default, warning banner, p-value gating.
- **Outcome-only SCM vs classic predictor-based SCM:** MVP approximation (§5 note) — acceptable for a first-pass tool, but state it; predictor covariates are a fast-follow.
- **Small donor pools:** p-value is meaningless below ~5 donors; gate the claim and warn loudly.
- **Over-trust in the memo:** the AI must downgrade confidence on weak fits rather than narrate a clean story (§7).

---

## 12. Optional Follow-up (not in this spec)

Scaffold the FastAPI service plus pytest cases for `/validate` and `/fit` directly from §4 and §9 to prove the spec is buildable end-to-end.
