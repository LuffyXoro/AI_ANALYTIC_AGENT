import sys
import os
import json
import argparse
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "alerts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "root_cause"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "analytics"))

from interpret_anomaly import interpret_anomaly
from tools import KNOWN_ANOMALIES

LOG_PATH = "data/processed/pipeline_run_log.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pipeline")


def run_pipeline(scenario_filter: str = None, send_alerts: bool = True) -> list:
    import pandas as pd

    logger.info("Pipeline run starting")
    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
    logger.info(f"Loaded {len(df):,} transactions")

    scenarios = KNOWN_ANOMALIES
    if scenario_filter:
        scenarios = [s for s in scenarios if s["id"] == scenario_filter]
        if not scenarios:
            logger.error(f"No known scenario with id '{scenario_filter}'")
            return []

    run_results = []
    for scenario in scenarios:
        logger.info(f"Processing {scenario['id']}: {scenario['metric']} "
                    f"{scenario['window_start']} to {scenario['window_end']}")
        try:
            seed = (
                {"region": scenario["region"], "category": scenario["category"]}
                if scenario.get("detection_mode") == "seeded" else None
            )
            result = interpret_anomaly(
                df,
                metric=scenario["metric"],
                window_start=scenario["window_start"],
                window_end=scenario["window_end"],
                seed_scope=seed,
                send_alert=send_alerts,
            )
            outcome = {
                "timestamp": datetime.now().isoformat(),
                "scenario_id": scenario["id"],
                "status": "success",
                "alert_result": result["alert_result"],
                "business_impact": result["evidence"]["business_impact"],
            }
            logger.info(f"  -> alert_result: {result['alert_result']}")
        except Exception as e:
            outcome = {
                "timestamp": datetime.now().isoformat(),
                "scenario_id": scenario["id"],
                "status": "error",
                "error": str(e),
            }
            logger.error(f"  -> FAILED: {e}")

        run_results.append(outcome)
        _append_log(outcome)

    logger.info(f"Pipeline run complete: {len(run_results)} scenario(s) processed")
    return run_results


def _append_log(outcome: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(outcome, default=str) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the anomaly detection -> interpretation -> alert pipeline")
    parser.add_argument("--scenario", type=str, default=None, help="Run only this scenario id (e.g. s1_south_electric_appliances -- see tools.py KNOWN_ANOMALIES)")
    parser.add_argument("--no-alert", action="store_true", help="Skip email alerting (evidence + LLM interpretation only)")
    args = parser.parse_args()

    results = run_pipeline(scenario_filter=args.scenario, send_alerts=not args.no_alert)
    print(f"\n{len(results)} scenario(s) processed. See {LOG_PATH} for the full audit log.")