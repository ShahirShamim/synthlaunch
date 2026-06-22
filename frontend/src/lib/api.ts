// Typed client for the SynthLaunch FastAPI backend.

export interface DatasetMeta {
  id: string
  kind: string
  title: string
  treated: string | null
  intervention: string | null
  metric_label: string
  description: string
  source?: string
  true_att?: number
}

export interface ValidationReport {
  ok: boolean
  errors: { code: string; message: string }[]
  warnings: { code: string; message: string }[]
  info: { units?: string[]; n_units?: number; date_range?: string[]; n_dates?: number }
}

export interface DatasetDetail {
  meta: DatasetMeta
  validation: ValidationReport
  records: { date: string; unit_id: string; metric: number }[]
}

export interface FitResult {
  treated_unit: string
  intervention_date: string
  dates: string[]
  donors: string[]
  weights: Record<string, number>
  treated: number[]
  synthetic: number[]
  naive_average: number[]
  gaps: number[]
  cumulative_gaps: number[]
  pre_mspe: number
  post_mspe: number
  rmspe_ratio: number
  att: number
  pct_lift: number
  n_pre: number
  n_post: number
  n_donors: number
}

export interface DidResult {
  att: number
  treated_pre_slope: number
  control_pre_slope: number
  parallel_trends_gap: number
  control_series: number[]
}

export interface PlaceboInSpace {
  dates: string[]
  intervention_date: string
  treated_unit: string
  paths: Record<string, number[]>
  ratios: Record<string, number>
  treated_ratio: number
  p_value: number
  p_value_pruned: number
  n_units: number
  n_kept: number
}

export interface PlaceboInTime {
  available: boolean
  fake_date?: string
  att?: number
}

export interface Confidence {
  confidence: "high" | "medium" | "low" | "insufficient"
  p_value: number
  n_donors: number
  n_pre: number
  reasons: string[]
}

export interface Memo {
  headline: string
  summary_markdown: string
  assumptions: string[]
  caveats: string[]
  generated_by?: string
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j))
  return j as T
}

export interface RunParams {
  dataset_id: string
  treated_unit: string
  intervention_date: string
}

export const listDatasets = () =>
  fetch("/api/datasets").then((r) => r.json()) as Promise<{ datasets: DatasetMeta[] }>

export const getDataset = (id: string) =>
  fetch(`/api/datasets/${id}`).then((r) => r.json()) as Promise<DatasetDetail>

export const fit = (p: RunParams) => post<{ fit: FitResult; did: DidResult }>("/api/fit", p)

export const analyze = (p: RunParams) =>
  post<{
    fit: FitResult; did: DidResult; in_space: PlaceboInSpace
    in_time: PlaceboInTime; confidence: Confidence
  }>("/api/analyze", p)

export const placebo = (p: RunParams) =>
  post<{ in_space: PlaceboInSpace; in_time: PlaceboInTime }>("/api/placebo", p)

export const generateMemo = (p: RunParams & { api_key?: string | null; model?: string | null }) =>
  post<{ memo: Memo; confidence: Confidence }>("/api/memo", p)

export async function uploadCsv(file: File): Promise<{ dataset_id: string; validation: ValidationReport }> {
  const fd = new FormData()
  fd.append("file", file)
  const r = await fetch("/api/datasets/upload", { method: "POST", body: fd })
  return r.json()
}
