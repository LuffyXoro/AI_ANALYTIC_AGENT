import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alerts"))
from evidence_packager import package_evidence
from llm_interface import get_llm_provider
from email_alert import maybe_alert

SYSTEM_PROMPT = """You are a business analytics interpreter. You will be given a JSON object containing PRE-COMPUTED, VERIFIED facts about a business anomaly -- KPI values, statistical contribution analysis, and an evidence chain. These numbers have already been calculated by tested statistical code. You must NEVER invent, estimate, or alter any number -- only reference numbers that appear in the JSON you're given.

Your job is to produce a business interpretation with these exact sections:

SITUATION: One sentence describing what happened, using only numbers from the evidence.
EVIDENCE: List the specific facts from the evidence_chain and business_impact that support this, citing exact figures.
MAIN DRIVER: Name the dimension/value combination that contributed most, per the evidence_chain.
BUSINESS IMPACT: State the shortfall/impact figure exactly as given.
POSSIBLE CAUSES: Your own reasoning about what might explain this pattern. Label this section clearly as HYPOTHESIS -- these are plausible explanations you are inferring, NOT facts from the data. The evidence shows correlation/pattern, not root cause in the human sense (e.g. WHY a stockout happened).
RECOMMENDED INVESTIGATION: What a human analyst should check next to confirm or rule out your hypotheses.
CONFIDENCE: A percentage reflecting how strong the statistical evidence is (not your certainty about the hypothesized causes). If low_sample_warning is present in the evidence, your confidence must be lower and you must mention the small sample size explicitly.

Do not use markdown headers with # symbols. Use the section names in plain caps as shown above."""


def interpret_anomaly(df, metric, window_start, window_end, seed_scope=None, send_alert: bool = True) -> dict:

    evidence = package_evidence(df, metric, window_start, window_end, seed_scope)
    evidence_json = json.dumps(evidence.to_dict(), indent=2, default=str)

    provider = get_llm_provider()
    interpretation = provider.complete(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"Here is the evidence:\n\n{evidence_json}",
    )

    alert_result = None
    if send_alert:
        alert_result = maybe_alert(evidence.to_dict(), llm_summary=interpretation)

    return {
        "evidence": evidence.to_dict(),   # the ground truth -- always available for the reader to check against
        "llm_interpretation": interpretation,
        "alert_result": alert_result,     # None if send_alert=False; otherwise {"sent": bool, "severity": ..., "reason"/"reasoning": ...}
    }


if __name__ == "__main__":
    import pandas as pd

    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])

    print("=== Interpreting Scenario 1 ===")
    result = interpret_anomaly(df, metric="sales", window_start="2022-06-01", window_end="2022-06-14")
    print("\n--- LLM Interpretation ---")
    print(result["llm_interpretation"])
    print("\n--- Alert Result ---")
    print(json.dumps(result["alert_result"], indent=2))
    print("\n--- (For reference) Ground-truth evidence the LLM was given ---")
    print(json.dumps(result["evidence"], indent=2, default=str))