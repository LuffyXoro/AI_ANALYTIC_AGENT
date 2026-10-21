"""
Run with: uvicorn src.api.main:app --reload --port 8000
Dashboard: http://localhost:8000/
Docs: http://localhost:8000/docs
"""

import sys
import os
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alerts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "root_cause"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analytics"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "anomaly_detection"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tools import tool_get_kpis, tool_get_trend, tool_get_root_cause, tool_list_known_anomalies, KNOWN_ANOMALIES
from run_pipeline import run_pipeline
from scan import scan_for_anomalies, scan_targeted, check_exact_window

app = FastAPI(
    title="AI Business Analytics & Anomaly Detection Agent",
    description="REST API wrapping the KPI engine, trend engine, anomaly detection, "
                 "root-cause analysis, and AI interpretation layers.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --- Request bodies ---
class AskRequest(BaseModel):
    question: str


class RunAnalysisRequest(BaseModel):
    scenario_id: Optional[str] = None  # None = run all known scenarios
    send_alerts: bool = True


class SendAlertRequest(BaseModel):
    scenario_id: str
    force: bool = True  # bypass severity threshold + cooldown, for manual testing


class ScanRequest(BaseModel):
    scan_start: str  # YYYY-MM-DD
    scan_end: str    # YYYY-MM-DD
    metric: str = "sales"
    region: Optional[str] = None
    category: Optional[str] = None  # if set -> TARGETED scan (needs region too); else BROAD scan
    send_alerts: bool = False  # opt-in, default OFF
    interpret_with_llm: bool = False


class CheckWindowRequest(BaseModel):
    window_start: str  # YYYY-MM-DD, exact window -- no scanning
    window_end: str
    region: str
    category: str
    metric: str = "sales"
    send_alerts: bool = False
    interpret_with_llm: bool = False


def _maybe_alert_and_interpret(evidence_like: dict, send_alerts: bool, interpret_with_llm: bool):
    """Shared helper: optionally run LLM interpretation, optionally send an
    alert with that interpretation attached. Used by /scan and /check-window."""
    summary = None
    if interpret_with_llm:
        try:
            from llm_interface import get_llm_provider
            from interpret_anomaly import SYSTEM_PROMPT
            import json
            provider = get_llm_provider()
            summary = provider.complete(SYSTEM_PROMPT, f"Here is the evidence:\n\n{json.dumps(evidence_like, indent=2, default=str)}")
        except Exception as e:
            summary = f"(LLM interpretation unavailable: {e})"

    alert_result = None
    if send_alerts:
        try:
            from email_alert import maybe_alert
            alert_result = maybe_alert(evidence_like, llm_summary=summary)
        except Exception as e:
            alert_result = {"sent": False, "reason": f"alert failed: {e}"}

    return summary, alert_result


# --- Endpoints ---

@app.get("/health")
def health():
    """Basic uptime check."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/")
def dashboard():
    """Serves the anomaly scanner web dashboard."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    return FileResponse(static_path)


@app.get("/kpis")
def get_kpis(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    region: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """Current KPI values for a date range, optionally filtered by region/category."""
    result = tool_get_kpis(start_date, end_date, region, category)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/trends")
def get_trends(
    metric: str = Query(..., description="e.g. sales, profit"),
    target_date: str = Query(..., description="YYYY-MM-DD"),
    period: str = Query("wow", description="dod, wow, mom, or yoy"),
    region: Optional[str] = Query(None),
):
    """How a metric changed vs. a prior period on a specific date."""
    try:
        return tool_get_trend(metric, target_date, period, region)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/anomalies")
def list_anomalies():
    """List anomalies this system has detected and verified (not a live scan -- see docs)."""
    return tool_list_known_anomalies()


@app.get("/anomalies/{anomaly_id}")
def get_anomaly(anomaly_id: str):
    """Detail on one specific known anomaly."""
    match = next((a for a in KNOWN_ANOMALIES if a["id"] == anomaly_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"No known anomaly with id '{anomaly_id}'")
    return match


@app.get("/root-cause/{anomaly_id}")
def get_root_cause(anomaly_id: str):
    """Evidence chain + business impact for one known anomaly, using its
    correct detection mode (blind vs. seeded -- see docs/04)."""
    match = next((a for a in KNOWN_ANOMALIES if a["id"] == anomaly_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"No known anomaly with id '{anomaly_id}'")

    seed_region = match["region"] if match.get("detection_mode") == "seeded" else None
    seed_category = match["category"] if match.get("detection_mode") == "seeded" else None

    return tool_get_root_cause(
        metric=match["metric"], window_start=match["window_start"], window_end=match["window_end"],
        region=seed_region, category=seed_category,
    )


@app.post("/ask")
def ask_question(request: AskRequest):
    """Natural-language Q&A -- the LLM decides which tool(s) to call.
    Requires GROQ_API_KEY to be set; returns 503 if the LLM call fails."""
    try:
        from qa_agent import ask
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Q&A agent unavailable: {e}")

    try:
        answer = ask(request.question)
        return {"question": request.question, "answer": answer}
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")


@app.post("/run-analysis")
def run_analysis(request: RunAnalysisRequest):
    """Manually trigger the full pipeline (evidence -> interpretation -> alert)
    for one or all known scenarios."""
    try:
        results = run_pipeline(scenario_filter=request.scenario_id, send_alerts=request.send_alerts)
        return {"scenarios_processed": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-alert")
def send_alert(request: SendAlertRequest):
    """Manually trigger an alert for a known scenario -- for testing the
    email pipeline without running the full LLM interpretation."""
    match = next((a for a in KNOWN_ANOMALIES if a["id"] == request.scenario_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"No known anomaly with id '{request.scenario_id}'")

    try:
        from evidence_packager import package_evidence
        from email_alert import maybe_alert
        import pandas as pd

        df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
        seed = ({"region": match["region"], "category": match["category"]}
                if match.get("detection_mode") == "seeded" else None)
        evidence = package_evidence(df, match["metric"], match["window_start"], match["window_end"], seed)

        result = maybe_alert(evidence.to_dict(), llm_summary="(manually triggered via /send-alert, no LLM call made)")
        return result
    except EnvironmentError as e:
        raise HTTPException(status_code=503, detail=f"Email not configured: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scan")
def scan(request: ScanRequest):
    """
    Discover anomalies over a date range.
    - No `category` given -> BROAD scan (region grain, auto-drilled). Reliable
      for loud, region-visible anomalies; free-form exploration.
    - `category` given (region required too) -> TARGETED scan (one specific
      region+category, fine grain). Real power for quieter anomalies, but
      you need to already suspect where to look.
    """
    import pandas as pd
    try:
        df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
        if request.category:
            if not request.region:
                raise HTTPException(status_code=400, detail="region is required when category is specified")
            hits = scan_targeted(df, request.scan_start, request.scan_end, region=request.region,
                                  category=request.category, metric=request.metric)
        else:
            hits = scan_for_anomalies(df, request.scan_start, request.scan_end,
                                       metric=request.metric, region_filter=request.region)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")

    alert_results = []
    for hit in hits:
        evidence_like = {
            "metric": hit["metric"], "window_start": hit["window_start"], "window_end": hit["window_end"],
            "seed_scope": {"region": hit["region"]},
            "business_impact": hit["business_impact"], "evidence_chain": hit["evidence_chain"],
            "volume_price_margin_check": hit["volume_price_margin_check"],
        }
        summary, alert_result = _maybe_alert_and_interpret(evidence_like, request.send_alerts, request.interpret_with_llm)
        hit["llm_interpretation"] = summary
        if alert_result:
            alert_results.append({"region": hit["region"], "window": f"{hit['window_start']} to {hit['window_end']}", **alert_result})

    return {
        "mode": "targeted" if request.category else "broad",
        "scan_start": request.scan_start, "scan_end": request.scan_end,
        "hits_found": len(hits), "hits": hits,
        "alerts_attempted": len(alert_results), "alert_results": alert_results,
        "limitation_note": (
            "Targeted scan: has real power for the specific combo given, but still requires enough "
            "signal strength to survive correction across the windows in this date range."
            if request.category else
            "Broad scan finds LOUD, region-visible anomalies. Quiet anomalies confined to a single "
            "category may not be detected this way -- use 'Verify a Window' instead."
        ),
    }


@app.post("/check-window")
def check_window(request: CheckWindowRequest):
    """
    Verify ONE specific window/region/category you already suspect -- no
    scanning, no multiple-testing correction, since there's only one
    hypothesis. The reliable way to confirm a quiet anomaly (like Scenario 2)
    that a scan across an uncertain range may miss.
    """
    import pandas as pd
    try:
        df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
        result = check_exact_window(df, request.window_start, request.window_end,
                                     region=request.region, category=request.category, metric=request.metric)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Check failed: {e}")

    evidence_like = {
        "metric": result["metric"], "window_start": result["window_start"], "window_end": result["window_end"],
        "seed_scope": {"region": result["region"], "category": result["category"]},
        "business_impact": result["business_impact"], "evidence_chain": result["evidence_chain"],
        "volume_price_margin_check": result["volume_price_margin_check"],
    }
    summary, alert_result = _maybe_alert_and_interpret(evidence_like, request.send_alerts, request.interpret_with_llm)
    result["llm_interpretation"] = summary
    result["alert_result"] = alert_result
    return result