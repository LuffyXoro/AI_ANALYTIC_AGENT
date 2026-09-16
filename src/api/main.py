import sys
import os
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alerts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "root_cause"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analytics"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.tools import tool_get_kpis, tool_get_trend, tool_get_root_cause, tool_list_known_anomalies, KNOWN_ANOMALIES
from run_pipeline import run_pipeline

app = FastAPI(
    title="AI Business Analytics & Anomaly Detection Agent",
    description="REST API wrapping the KPI engine, trend engine, anomaly detection, "
                 "root-cause analysis, and AI interpretation layers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --- Request bodies ---
class AskRequest(BaseModel):
    question: str


class RunAnalysisRequest(BaseModel):
    scenario_id: Optional[str] = None  
    send_alerts: bool = True


class SendAlertRequest(BaseModel):
    scenario_id: str
    force: bool = True  


# --- Endpoints ---

@app.get("/health")
def health():
    """Basic uptime check."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/kpis")
def get_kpis(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    region: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
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
    try:
        return tool_get_trend(metric, target_date, period, region)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/anomalies")
def list_anomalies():
    return tool_list_known_anomalies()


@app.get("/anomalies/{anomaly_id}")
def get_anomaly(anomaly_id: str):
   
    match = next((a for a in KNOWN_ANOMALIES if a["id"] == anomaly_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"No known anomaly with id '{anomaly_id}'")
    return match


@app.get("/root-cause/{anomaly_id}")
def get_root_cause(anomaly_id: str):
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
    try:
        from agent.qa_agent import ask
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
    try:
        results = run_pipeline(scenario_filter=request.scenario_id, send_alerts=request.send_alerts)
        return {"scenarios_processed": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-alert")
def send_alert(request: SendAlertRequest):
    match = next((a for a in KNOWN_ANOMALIES if a["id"] == request.scenario_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"No known anomaly with id '{request.scenario_id}'")

    try:
        from agent.evidence_packager import package_evidence
        from alerts.email_alert import maybe_alert
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