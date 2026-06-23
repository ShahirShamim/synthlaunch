"""AI Causal Product Memo.

If an Anthropic API key is available (passed per-request or via ANTHROPIC_API_KEY),
the memo is written by Claude using a forced tool call so the output is structured.
Otherwise a deterministic template memo is built from the numbers, so the demo works
fully offline. Either way the *confidence label and numbers are computed in Python* —
the model only writes prose and must respect them (no invented ROI, no upgrading a
weak result).
"""
from __future__ import annotations

import json
import os

DEFAULT_MODEL = os.environ.get("SYNTHLAUNCH_MODEL", "claude-haiku-4-5-20251001")

_MEMO_TOOL = {
    "name": "write_causal_memo",
    "description": "Write a product memo summarising a synthetic-control causal analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One-line takeaway."},
            "summary_markdown": {"type": "string",
                                 "description": "2-4 short paragraphs of markdown. State the ATT, % lift and empirical p-value exactly as provided. Do not invent monetary ROI."},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "caveats": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["headline", "summary_markdown", "assumptions", "caveats"],
    },
}

_SYSTEM = (
    "You are a careful causal-inference analyst writing a product memo. "
    "Use ONLY the numbers provided; never invent monetary ROI unless unit economics "
    "are given. Respect the provided confidence label exactly — if it is 'low' or "
    "'insufficient', say plainly that the effect is not reliably distinguishable from "
    "noise. Always restate the key assumptions (the intervention date was fixed in "
    "advance, donor units were untreated, and DiD additionally assumes parallel "
    "pre-trends)."
)


def _context(meta, fit, did_res, placebo, confidence, intervals=None) -> dict:
    ci = {}
    if intervals and intervals.get("available"):
        ci = {
            "att_ci_low": round(intervals["att_low"], 4),
            "att_ci_high": round(intervals["att_high"], 4),
            "pct_ci_low": round(intervals["pct_low"], 3),
            "pct_ci_high": round(intervals["pct_high"], 3),
        }
    return {
        **ci,
        "treated_unit": fit["treated_unit"],
        "intervention_date": fit["intervention_date"],
        "metric_label": meta.get("metric_label", "metric"),
        "att": round(fit["att"], 4),
        "pct_lift": round(fit["pct_lift"], 3),
        "pre_mspe": round(fit["pre_mspe"], 5),
        "post_mspe": round(fit["post_mspe"], 5),
        "rmspe_ratio": round(fit["rmspe_ratio"], 3),
        "p_value": round(placebo["p_value"], 4),
        "p_value_pruned": round(placebo["p_value_pruned"], 4),
        "n_donors": fit["n_donors"],
        "n_pre": fit["n_pre"],
        "n_post": fit["n_post"],
        "top_donors": sorted(fit["weights"].items(), key=lambda kv: -kv[1])[:5],
        "did_att": round(did_res["att"], 4),
        "parallel_trends_gap": round(did_res["parallel_trends_gap"], 5),
        "confidence": confidence["confidence"],
        "confidence_reasons": confidence["reasons"],
    }


def _template_memo(ctx: dict) -> dict:
    direction = "decrease" if ctx["att"] < 0 else "increase"
    donors = ", ".join(f"{u} ({w:.0%})" for u, w in ctx["top_donors"] if w > 0.001)
    sig = {
        "high": "statistically distinguishable from placebo noise",
        "medium": "suggestive but not conclusive",
        "low": "NOT reliably distinguishable from placebo noise",
        "insufficient": "NOT interpretable — the data does not support inference",
    }[ctx["confidence"]]
    ci_txt = ""
    if "att_ci_low" in ctx:
        ci_txt = (f" The placebo-based 95% interval runs from {ctx['att_ci_low']:.2f} to "
                  f"{ctx['att_ci_high']:.2f} ({ctx['pct_ci_low']:.1f}% to {ctx['pct_ci_high']:.1f}%).")
    summary = (
        f"After the intervention on **{ctx['intervention_date']}**, {ctx['treated_unit']}'s "
        f"{ctx['metric_label']} shows an estimated average treatment effect (ATT) of "
        f"**{ctx['att']:.2f}** ({ctx['pct_lift']:.1f}% {direction}) versus its synthetic control.{ci_txt}\n\n"
        f"The synthetic control is built mainly from {donors}. Pre-treatment fit "
        f"(MSPE = {ctx['pre_mspe']:.3f}) and a placebo permutation test give an empirical "
        f"**p-value = {ctx['p_value']:.3f}** ({ctx['n_donors']} donors, {ctx['n_pre']} pre-periods). "
        f"The DiD baseline estimates an ATT of {ctx['did_att']:.2f}.\n\n"
        f"**Confidence: {ctx['confidence'].upper()}** — the effect is {sig}. "
        f"{'; '.join(ctx['confidence_reasons'])}."
    )
    return {
        "headline": f"{ctx['treated_unit']}: estimated {ctx['pct_lift']:.1f}% {direction} "
                    f"(p={ctx['p_value']:.3f}, confidence {ctx['confidence']})",
        "summary_markdown": summary,
        "assumptions": [
            "The intervention date was fixed in advance, not chosen to maximise the effect.",
            "Donor units were not themselves affected by the intervention.",
            "DiD additionally assumes parallel pre-treatment trends "
            f"(pre-slope gap = {ctx['parallel_trends_gap']:.4f}).",
        ],
        "caveats": ctx["confidence_reasons"] + (
            ["Fewer than 5 donors: treat the p-value as indicative only."]
            if ctx["n_donors"] < 5 else []),
        "generated_by": "template (no API key)",
    }


def build_memo(meta, fit, did_res, placebo, confidence, intervals=None,
               api_key: str | None = None, model: str | None = None) -> dict:
    ctx = _context(meta, fit, did_res, placebo, confidence, intervals)
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _template_memo(ctx)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=key)
        resp = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=1200,
            system=_SYSTEM,
            tools=[_MEMO_TOOL],
            tool_choice={"type": "tool", "name": "write_causal_memo"},
            messages=[{"role": "user", "content":
                       "Write the causal product memo for this analysis. "
                       "Numbers (use exactly):\n```json\n" + json.dumps(ctx, indent=2) + "\n```"}],
        )
        for block in resp.content:
            if block.type == "tool_use":
                out = dict(block.input)
                out["generated_by"] = f"Claude ({model or DEFAULT_MODEL})"
                return out
        return _template_memo(ctx)  # model didn't call the tool
    except Exception as exc:  # network / key / SDK error -> graceful offline fallback
        out = _template_memo(ctx)
        out["generated_by"] = f"template (API error: {type(exc).__name__})"
        return out
