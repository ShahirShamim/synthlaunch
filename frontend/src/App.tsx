import { useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import { toast } from "sonner"
import { Toaster } from "@/components/ui/sonner"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip"
import { Chart } from "@/components/Chart"
import { HowToRead } from "@/components/HowToRead"
import type { Explainer } from "@/components/HowToRead"
import * as api from "@/lib/api"
import type {
  Confidence, DatasetMeta, DidResult, FitResult, Memo,
  PlaceboInSpace, PlaceboInTime,
} from "@/lib/api"

const ROSE = "#f43f5e"
const INDIGO = "#818cf8"
const GREY = "#71717a"
const EMERALD = "#34d399"

const CONF: Record<Confidence["confidence"], { label: string; cls: string }> = {
  high: { label: "High confidence", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" },
  medium: { label: "Medium confidence", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" },
  low: { label: "Low confidence", cls: "bg-rose-500/15 text-rose-400 border-rose-500/30" },
  insufficient: { label: "Insufficient data", cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30" },
}

function vline(date: string) {
  return {
    shapes: [{ type: "line", x0: date, x1: date, yref: "paper", y0: 0, y1: 1,
      line: { color: "#f59e0b", width: 1.5, dash: "dot" } }],
    annotations: [{ x: date, y: 1, yref: "paper", text: "launch", showarrow: false,
      font: { color: "#f59e0b", size: 11 }, yshift: 8 }],
  }
}

// Minimal markdown: paragraphs, **bold**, and "- " bullet lists.
function bold(s: string) {
  return s.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i} className="text-foreground">{p.slice(2, -2)}</strong>
      : <span key={i}>{p}</span>)
}
function Md({ text }: { text: string }) {
  const blocks = text.split(/\n\n+/)
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        const lines = b.split("\n")
        if (lines.every((l) => l.trim().startsWith("- "))) {
          return (
            <ul key={i} className="list-disc space-y-1 pl-5">
              {lines.map((l, j) => <li key={j}>{bold(l.replace(/^\s*-\s/, ""))}</li>)}
            </ul>
          )
        }
        return <p key={i}>{bold(b)}</p>
      })}
    </div>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card/50 px-3 py-2">
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        {label}
        {hint && (
          <Tooltip>
            <TooltipTrigger className="cursor-help text-muted-foreground/70">ⓘ</TooltipTrigger>
            <TooltipContent className="max-w-xs">{hint}</TooltipContent>
          </Tooltip>
        )}
      </div>
      <div className="font-semibold tabular-nums">{value}</div>
    </div>
  )
}

function ChartCard({ title, desc, explainer, children }: {
  title: string; desc: string; explainer: Explainer; children: ReactNode
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{desc}</CardDescription>
      </CardHeader>
      <CardContent>
        {children}
        <HowToRead explainer={explainer} />
      </CardContent>
    </Card>
  )
}

export default function App() {
  const [datasets, setDatasets] = useState<DatasetMeta[]>([])
  const [dsId, setDsId] = useState<string>("")
  const [meta, setMeta] = useState<DatasetMeta | null>(null)
  const [units, setUnits] = useState<string[]>([])
  const [allDates, setAllDates] = useState<string[]>([])
  const [treated, setTreated] = useState<string>("")
  const [date, setDate] = useState<string>("")
  const [explore, setExplore] = useState(false)

  const [running, setRunning] = useState(false)
  const [fit, setFit] = useState<FitResult | null>(null)
  const [did, setDid] = useState<DidResult | null>(null)
  const [inSpace, setInSpace] = useState<PlaceboInSpace | null>(null)
  const [inTime, setInTime] = useState<PlaceboInTime | null>(null)
  const [conf, setConf] = useState<Confidence | null>(null)

  const [apiKey, setApiKey] = useState("")
  const [model, setModel] = useState("")
  const [memo, setMemo] = useState<Memo | null>(null)
  const [memoing, setMemoing] = useState(false)

  async function selectDataset(id: string, list = datasets) {
    setDsId(id)
    setFit(null); setInSpace(null); setMemo(null); setConf(null)
    const m = list.find((x) => x.id === id) ?? null
    setMeta(m)
    const detail = await api.getDataset(id)
    const us = detail.validation.info.units ?? []
    setUnits(us)
    setAllDates([...new Set(detail.records.map((r) => r.date))].sort())
    setTreated(m?.treated && us.includes(m.treated) ? m.treated : us[0] ?? "")
    setDate(m?.intervention ?? "")
    if (!detail.validation.ok) {
      toast.error("Dataset failed validation: " +
        detail.validation.errors.map((x) => x.message).join("; "))
    }
  }

  useEffect(() => {
    api.listDatasets().then((d) => {
      setDatasets(d.datasets)
      if (d.datasets.length) selectDataset(d.datasets[0].id, d.datasets)
    }).catch((e) => toast.error("Failed to load datasets: " + e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function run(useDate = date) {
    if (!dsId || !treated || !useDate) return
    setRunning(true)
    const params = { dataset_id: dsId, treated_unit: treated, intervention_date: useDate }
    try {
      if (explore) {
        const { fit: f, did: d } = await api.fit(params)
        setFit(f); setDid(d); setInSpace(null); setConf(null); setMemo(null)
      } else {
        const a = await api.analyze(params)
        setFit(a.fit); setDid(a.did); setInSpace(a.in_space)
        setInTime(a.in_time); setConf(a.confidence); setMemo(null)
      }
    } catch (e) {
      toast.error("Analysis failed: " + (e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  async function genMemo() {
    if (!dsId || !treated || !date) return
    setMemoing(true)
    try {
      const r = await api.generateMemo({
        dataset_id: dsId, treated_unit: treated, intervention_date: date,
        api_key: apiKey || null, model: model || null,
      })
      setMemo(r.memo); setConf(r.confidence)
    } catch (e) {
      toast.error("Memo failed: " + (e as Error).message)
    } finally {
      setMemoing(false)
    }
  }

  async function onUpload(file: File) {
    const r = await api.uploadCsv(file)
    const d = await api.listDatasets()
    setDatasets(d.datasets)
    if (r.validation.ok) {
      await selectDataset(r.dataset_id, d.datasets)
      toast.success("Uploaded — set the treated unit & date, then Run.")
    } else {
      toast.error("Uploaded but invalid: " + r.validation.errors.map((x) => x.message).join("; "))
    }
  }

  const metricLabel = meta?.metric_label ?? "metric"
  const plain = useMemo(() => {
    if (!fit) return null
    const dir = fit.att < 0 ? "lower" : "higher"
    const att = Math.abs(fit.att)
    const pct = Math.abs(fit.pct_lift)
    let sig = ""
    if (conf && !explore) {
      const p = inSpace?.p_value ?? conf.p_value
      sig = {
        high: ` This gap is extreme compared with the placebo checks (p = ${p.toFixed(3)}), so it is unlikely to be chance.`,
        medium: ` This is suggestive (p = ${p.toFixed(3)}) but not conclusive.`,
        low: ` Similar-sized gaps also appear for control units (p = ${p.toFixed(3)}), so we cannot rule out chance.`,
        insufficient: ` There is not enough data to judge significance — treat this as exploratory.`,
      }[conf.confidence]
    }
    return `After ${fit.intervention_date}, ${fit.treated_unit}'s ${metricLabel} was about `
      + `${att.toLocaleString(undefined, { maximumFractionDigits: 2 })} (${pct.toFixed(1)}%) ${dir} `
      + `than the synthetic estimate of what would have happened without the change.${sig}`
  }, [fit, conf, inSpace, explore, metricLabel])

  return (
    <TooltipProvider delay={150}>
      <Toaster richColors theme="dark" position="top-center" />
      <div className="mx-auto max-w-7xl p-5">
        <header className="mb-5">
          <h1 className="text-2xl font-bold tracking-tight">🚀 SynthLaunch</h1>
          <p className="text-sm text-muted-foreground">
            Measure the impact of a launch you couldn't A/B test. We build a “synthetic twin” of the
            treated unit from untreated comparisons, then read off the gap after launch.
          </p>
        </header>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[330px_1fr]">
          {/* ---------------- CONTROLS ---------------- */}
          <aside className="space-y-4">
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">1 · Choose data</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5">
                  <Label>Dataset</Label>
                  <Select value={dsId} onValueChange={(v) => v && selectDataset(v)}>
                    <SelectTrigger><SelectValue placeholder="Select a dataset" /></SelectTrigger>
                    <SelectContent>
                      {datasets.map((d) => <SelectItem key={d.id} value={d.id}>{d.title}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {meta && <p className="text-xs text-muted-foreground">{meta.description}</p>}
                </div>
                <div className="space-y-1.5">
                  <Label className="text-muted-foreground">Or upload a tidy CSV</Label>
                  <Input type="file" accept=".csv" className="text-xs"
                    onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
                  <p className="text-[11px] text-muted-foreground">columns: date, unit_id, metric</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">2 · Configure</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5">
                  <Label>Treated unit (what got the change)</Label>
                  <Select value={treated} onValueChange={(v) => v && setTreated(v)}>
                    <SelectTrigger><SelectValue placeholder="unit" /></SelectTrigger>
                    <SelectContent className="max-h-72">
                      {units.map((u) => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Launch / intervention date</Label>
                  <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
                </div>

                <div className="rounded-lg border p-3">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="explore" className="cursor-pointer">Exploration mode</Label>
                    <Switch id="explore" checked={explore} onCheckedChange={setExplore} />
                  </div>
                  {explore && (
                    <div className="mt-3 space-y-2">
                      <input type="range" min={1} max={Math.max(1, allDates.length - 2)}
                        className="w-full accent-amber-500"
                        defaultValue={Math.max(1, allDates.indexOf(date))}
                        onChange={(e) => { const d = allDates[+e.target.value]; if (d) { setDate(d); run(d) } }} />
                      <p className="text-[11px] text-amber-400">
                        ⚠ Sensitivity check only. Sliding the date to maximise the effect is p-hacking,
                        not a valid estimate — significance is disabled here.
                      </p>
                    </div>
                  )}
                </div>

                <Button className="w-full" disabled={running || !treated} onClick={() => run()}>
                  {running ? "Running…" : "Run analysis"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">3 · AI memo (optional)</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input type="password" placeholder="Anthropic API key (optional)"
                  value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
                <Input placeholder="model (default claude-haiku-4-5)" value={model}
                  onChange={(e) => setModel(e.target.value)} />
                <Button variant="secondary" className="w-full" disabled={!fit || explore || memoing} onClick={genMemo}>
                  {memoing ? "Writing…" : "Generate product memo"}
                </Button>
                <p className="text-[11px] text-muted-foreground">
                  No key → a clear template memo is built from the numbers (works offline).
                </p>
              </CardContent>
            </Card>
          </aside>

          {/* ---------------- RESULTS ---------------- */}
          <main className="space-y-5">
            {!fit && (
              <Alert>
                <AlertTitle>Pick a dataset and hit “Run analysis”.</AlertTitle>
                <AlertDescription>
                  Try <span className="font-medium">California Prop 99</span> (a real tobacco-tax study) or
                  the <span className="font-medium">Brexit</span> UK example. Every chart has a “How to read this” explainer.
                </AlertDescription>
              </Alert>
            )}

            {explore && fit && (
              <Alert className="border-amber-500/40 bg-amber-500/5">
                <AlertTitle className="text-amber-400">Exploration mode — not a valid estimate</AlertTitle>
                <AlertDescription>You're sliding the launch date manually. Turn this off and Run for a real, significance-tested result.</AlertDescription>
              </Alert>
            )}

            {/* Headline */}
            {fit && (
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle>Result</CardTitle>
                    {conf && !explore && (
                      <Badge variant="outline" className={CONF[conf.confidence].cls}>{CONF[conf.confidence].label}</Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {plain && <p className="text-[15px] leading-relaxed">{plain}</p>}
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Stat label="Effect (ATT)" value={fit.att.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      hint="Average Treatment effect on the Treated: the average gap between the real unit and its synthetic twin after launch." />
                    <Stat label="% change" value={`${fit.pct_lift.toFixed(1)}%`}
                      hint="The effect as a percentage of the synthetic twin's level." />
                    {!explore && inSpace && (
                      <Stat label="p-value" value={inSpace.p_value.toFixed(3)}
                        hint="Share of units (incl. placebos) whose effect is at least as extreme as the treated unit's. Smaller = less likely to be chance." />
                    )}
                    {did && (
                      <Stat label="DiD check" value={did.att.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        hint="A simpler Difference-in-Differences estimate, shown for comparison. It should be in the same ballpark." />
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>Pre-launch fit (MSPE): <b className="text-foreground">{fit.pre_mspe.toFixed(3)}</b> — lower means the twin tracked well before launch.</span>
                    <span>{fit.n_donors} donor units · {fit.n_pre} pre-periods</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 1 · main comparison */}
            {fit && (
              <ChartCard
                title="1 · Did the launch change things?"
                desc="The treated unit vs its synthetic twin over time."
                explainer={{
                  what: `Red is the real ${fit.treated_unit}. Blue is its “synthetic twin” — a blend of comparison units built to copy it. Grey dashed is a plain average of all comparisons. The dotted vertical line is the launch.`,
                  read: "Before the launch line, red and blue should sit almost on top of each other (the twin is a good stand-in). After the launch, the vertical gap between red and blue is the estimated effect. The grey average usually doesn't track red — that's why a naive before/after misleads.",
                  tells: "How big the impact was, and whether to trust it: good overlap before launch means the twin is credible.",
                }}>
                <Chart
                  data={[
                    { x: fit.dates, y: fit.treated, name: fit.treated_unit, mode: "lines", line: { color: ROSE, width: 2.5 } },
                    { x: fit.dates, y: fit.synthetic, name: "Synthetic twin", mode: "lines", line: { color: INDIGO, width: 2.5 } },
                    { x: fit.dates, y: fit.naive_average, name: "Naive average", mode: "lines", line: { color: GREY, width: 1, dash: "dash" } },
                  ]}
                  layout={vline(fit.intervention_date)}
                />
              </ChartCard>
            )}

            {fit && (
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
                <ChartCard
                  title="2 · Total effect over time"
                  desc="Running sum of the gap (treated − synthetic)."
                  explainer={{
                    what: "Each point adds up the gap so far — the cumulative effect since the start.",
                    read: "It should hug zero before the launch. After launch it slopes away from zero; the final value is the total accumulated effect.",
                    tells: `The net cumulative impact on ${metricLabel} — e.g. total units gained or lost.`,
                  }}>
                  <Chart
                    data={[{ x: fit.dates, y: fit.cumulative_gaps, fill: "tozeroy", mode: "lines", line: { color: EMERALD }, name: "cumulative" }]}
                    layout={vline(fit.intervention_date)} height={300}
                  />
                </ChartCard>

                <ChartCard
                  title="3 · What the twin is made of"
                  desc="The comparison units that compose the synthetic twin."
                  explainer={{
                    what: "The synthetic twin is a weighted recipe of comparison units. Each slice is one unit's weight.",
                    read: "Bigger slice = that unit matters more in mimicking the treated unit before launch. Units with ~0 weight aren't shown.",
                    tells: "Which comparisons your result leans on. If one small or unusual unit dominates, be cautious.",
                  }}>
                  <Chart
                    data={[{
                      type: "pie", hole: 0.55,
                      labels: Object.keys(fit.weights).filter((k) => fit.weights[k] > 0.001),
                      values: Object.keys(fit.weights).filter((k) => fit.weights[k] > 0.001).map((k) => fit.weights[k]),
                      textinfo: "label+percent", textfont: { size: 11 },
                      marker: { line: { color: "#0a0a0a", width: 1 } },
                    }]}
                    layout={{ showlegend: false }} height={300}
                  />
                </ChartCard>
              </div>
            )}

            {/* 4 · placebo */}
            {!explore && inSpace && fit && (
              <ChartCard
                title="4 · Is it real, or just noise?"
                desc={`Placebo test — empirical p = ${inSpace.p_value.toFixed(3)}`}
                explainer={{
                  what: `We pretend every comparison unit was the “treated” one and re-run the analysis. Grey lines are those fake effects (should wiggle near zero). Red is the real ${fit.treated_unit}.`,
                  read: "If red clearly pulls away from the grey crowd after the launch, the real effect stands out from noise. The p-value counts how many units (real + placebos) have an effect at least as extreme as the treated one.",
                  tells: `Statistical significance. p = ${inSpace.p_value.toFixed(3)} means about ${Math.round(inSpace.p_value * inSpace.n_units)} of ${inSpace.n_units} units look this extreme.${inTime?.available ? ` A back-dated “fake launch” test gives ${inTime.att?.toFixed(2)} (should be near 0).` : ""}`,
                }}>
                <Chart
                  data={Object.entries(inSpace.paths).map(([u, g]) => {
                    const isT = u === inSpace.treated_unit
                    return { x: inSpace.dates, y: g, mode: "lines", name: isT ? u : "",
                      showlegend: isT, hoverinfo: isT ? "all" : "skip",
                      line: { color: isT ? ROSE : "rgba(161,161,170,0.22)", width: isT ? 3 : 1 } }
                  })}
                  layout={{
                    ...vline(inSpace.intervention_date),
                    shapes: [
                      ...vline(inSpace.intervention_date).shapes,
                      { type: "line", x0: inSpace.dates[0], x1: inSpace.dates[inSpace.dates.length - 1], y0: 0, y1: 0, line: { color: "#52525b", width: 1 } },
                    ],
                  }}
                  height={360}
                />
              </ChartCard>
            )}

            {/* memo */}
            {memo && (
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Causal product memo</CardTitle>
                    <span className="text-xs text-muted-foreground">{memo.generated_by}</span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="font-medium">{memo.headline}</p>
                  <Md text={memo.summary_markdown} />
                  {memo.assumptions?.length > 0 && (
                    <>
                      <Separator />
                      <div>
                        <p className="mb-1 text-sm font-medium">Assumptions</p>
                        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                          {memo.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                        </ul>
                      </div>
                    </>
                  )}
                  {memo.caveats?.length > 0 && (
                    <div>
                      <p className="mb-1 text-sm font-medium">Caveats</p>
                      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                        {memo.caveats.map((c, i) => <li key={i}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
