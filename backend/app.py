"""SynthLaunch FastAPI app: validation + SCM + DiD + placebo + AI memo, and it
serves the single-page frontend so the whole demo runs from one process."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from synthlaunch import datasets, memo, scm, validation

load_dotenv()

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT.parent / "frontend" / "dist"  # built Vite app (run: npm run build)

app = FastAPI(title="SynthLaunch", version="0.1.0")


class FitRequest(BaseModel):
    dataset_id: str
    treated_unit: str
    intervention_date: str
    columns: dict | None = None


class MemoRequest(FitRequest):
    api_key: str | None = None
    model: str | None = None


def _load_validated(req: FitRequest):
    try:
        df = datasets.get_dataframe(req.dataset_id)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {req.dataset_id!r}")
    df = validation.normalise(df, req.columns)
    base = validation.validate(df)
    if not base.ok:
        raise HTTPException(422, {"stage": "panel", **base.to_dict()})
    gate = validation.check_intervention(df, req.treated_unit, req.intervention_date)
    if not gate.ok:
        raise HTTPException(422, {"stage": "intervention", **gate.to_dict()})
    return df, base, gate


@app.get("/api/datasets")
def api_datasets():
    return {"datasets": datasets.list_datasets()}


@app.get("/api/datasets/{ds_id}")
def api_dataset(ds_id: str):
    try:
        df = datasets.get_dataframe(ds_id)
        meta = datasets.get_meta(ds_id)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {ds_id!r}")
    report = validation.validate(df)
    records = validation.normalise(df).to_dict("records") if report.ok else []
    return {"meta": {k: v for k, v in meta.items() if k != "file"},
            "validation": report.to_dict(), "records": records}


@app.post("/api/datasets/upload")
async def api_upload(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        ds_id, df = datasets.register_upload(raw, file.filename or "upload.csv")
    except Exception as exc:
        raise HTTPException(400, f"could not parse CSV: {exc}")
    report = validation.validate(df)
    return {"dataset_id": ds_id, "validation": report.to_dict(),
            "meta": datasets.get_meta(ds_id)}


@app.post("/api/validate")
def api_validate(req: FitRequest):
    df = validation.normalise(datasets.get_dataframe(req.dataset_id), req.columns)
    return {"panel": validation.validate(df).to_dict(),
            "intervention": validation.check_intervention(
                df, req.treated_unit, req.intervention_date).to_dict()}


@app.post("/api/fit")
def api_fit(req: FitRequest):
    df, _, _ = _load_validated(req)
    wide = scm.pivot_panel(df)
    fit = scm.synthetic_control(wide, req.treated_unit, req.intervention_date)
    did_res = scm.did(wide, req.treated_unit, req.intervention_date)
    return {"fit": fit.to_dict(), "did": did_res}


@app.post("/api/placebo")
def api_placebo(req: FitRequest):
    df, _, _ = _load_validated(req)
    wide = scm.pivot_panel(df)
    in_space = scm.placebo_in_space(wide, req.treated_unit, req.intervention_date)
    in_time = scm.placebo_in_time(wide, req.treated_unit, req.intervention_date)
    return {"in_space": in_space, "in_time": in_time}


@app.post("/api/analyze")
def api_analyze(req: FitRequest):
    """Everything the dashboard needs in one call: SCM fit, DiD baseline, in-space +
    in-time placebo, and the confidence label (placebo computed once)."""
    df, _, _ = _load_validated(req)
    wide = scm.pivot_panel(df)
    fit = scm.synthetic_control(wide, req.treated_unit, req.intervention_date)
    did_res = scm.did(wide, req.treated_unit, req.intervention_date)
    in_space = scm.placebo_in_space(wide, req.treated_unit, req.intervention_date)
    in_time = scm.placebo_in_time(wide, req.treated_unit, req.intervention_date)
    confidence = scm.compute_confidence(fit, in_space)
    return {"fit": fit.to_dict(), "did": did_res, "in_space": in_space,
            "in_time": in_time, "confidence": confidence}


@app.post("/api/memo")
def api_memo(req: MemoRequest):
    df, _, _ = _load_validated(req)
    wide = scm.pivot_panel(df)
    fit = scm.synthetic_control(wide, req.treated_unit, req.intervention_date)
    did_res = scm.did(wide, req.treated_unit, req.intervention_date)
    placebo = scm.placebo_in_space(wide, req.treated_unit, req.intervention_date)
    confidence = scm.compute_confidence(fit, placebo)
    meta = datasets.get_meta(req.dataset_id)
    result = memo.build_memo(meta, fit.to_dict(), did_res, placebo, confidence,
                             api_key=req.api_key, model=req.model)
    return {"memo": result, "confidence": confidence}


@app.get("/")
def index():
    idx = FRONTEND / "index.html"
    if not idx.exists():
        raise HTTPException(503, "frontend not built — run `npm --prefix frontend run build`")
    return FileResponse(idx)


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
