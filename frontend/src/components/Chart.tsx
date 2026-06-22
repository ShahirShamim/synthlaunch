import { useEffect, useRef } from "react"
import Plotly from "plotly.js-dist-min"

type Props = { data: unknown[]; layout?: Record<string, unknown>; height?: number }

// Thin React wrapper around plotly.js. Dark, chrome-free styling to match the UI.
export function Chart({ data, layout, height = 340 }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const base = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#a1a1aa", size: 12 },
      margin: { l: 52, r: 18, t: 12, b: 40 },
      legend: { orientation: "h", y: -0.2, x: 0 },
      xaxis: { gridcolor: "rgba(255,255,255,0.06)", zeroline: false },
      yaxis: { gridcolor: "rgba(255,255,255,0.06)", zeroline: false },
      hovermode: "x unified",
      ...layout,
    }
    Plotly.react(el, data, base, { displayModeBar: false, responsive: true })
  }, [data, layout])

  useEffect(() => {
    const el = ref.current
    return () => {
      if (el) Plotly.purge(el)
    }
  }, [])

  return <div ref={ref} style={{ width: "100%", height }} />
}
