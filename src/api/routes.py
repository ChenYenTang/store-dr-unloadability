from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse, RedirectResponse
from datetime import datetime
from typing import Dict, Any

from src.io.schema import EvaluateRequest
from src.policy.config_loader import load_config
from src.policy.scoring import prioritize

app = FastAPI(title="Store DR Unloadability API")
router = APIRouter(prefix="/api/v1")

@app.get("/")  # 根路徑 → /ui
def root_redirect():
    return RedirectResponse(url="/ui", status_code=307)

@router.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "ts": datetime.now().isoformat(timespec="seconds")}

@router.get("/version")
def version() -> Dict[str, Any]:
    return {"app": "store-dr-unloadability", "version": "0.1.0", "model_version": "demo-heuristic-001"}

@router.post("/evaluate")
def evaluate(req: EvaluateRequest):
    cfg = load_config()
    cabs = [c.dict() for c in req.cabinets]
    results_sorted = prioritize(cabs, req.business_hours_flag, cfg)
    ranked_ids = [r["cabinet_id"] for r in results_sorted]
    return JSONResponse({
        "store_id": req.store_id,
        "evaluated_at": req.timestamp,
        "targets": {"kw_reduction_goal": None},
        "cabinets": results_sorted,
        "ranked_cabinet_ids": ranked_ids
    })

app.include_router(router)
