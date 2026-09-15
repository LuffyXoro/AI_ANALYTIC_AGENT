import os
import sys
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from severity import classify_severity, Severity

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

COOLDOWN_STATE_PATH = "data/processed/alert_cooldown_state.json"
COOLDOWN_HOURS = 24  # don't re-alert on the same anomaly scope within this window


def _cooldown_key(metric: str, window_start: str, window_end: str, region: str = None, category: str = None) -> str:
    return f"{metric}|{window_start}|{window_end}|{region or 'ALL'}|{category or 'ALL'}"


def _load_cooldown_state() -> dict:
    if os.path.exists(COOLDOWN_STATE_PATH):
        with open(COOLDOWN_STATE_PATH) as f:
            return json.load(f)
    return {}


def _save_cooldown_state(state: dict):
    os.makedirs(os.path.dirname(COOLDOWN_STATE_PATH), exist_ok=True)
    with open(COOLDOWN_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _is_in_cooldown(key: str, state: dict) -> bool:
    if key not in state:
        return False
    last_sent = datetime.fromisoformat(state[key])
    return datetime.now() - last_sent < timedelta(hours=COOLDOWN_HOURS)


def build_alert_email(evidence: dict, severity: Severity, llm_summary: str = None) -> str:
    """Plain-text email body -- matches the fields your brief's Section 20 lists:
    metric, actual, expected, deviation, severity, main contributor, business impact, AI summary."""
    impact = evidence["business_impact"]
    chain = evidence["evidence_chain"]
    main_contributor = next((s for s in chain if "value" in s), {})

    lines = [
        f"ANOMALY ALERT -- Severity: {severity.value}",
        "=" * 50,
        f"Metric: {impact['metric']}",
        f"Period: {evidence['window_start']} to {evidence['window_end']}",
        f"Actual: {impact['actual']:,.2f}",
        f"Expected: {impact['expected']:,.2f}",
        f"Shortfall: {impact['shortfall']:,.2f} ({impact['pct_change']}%)",
        "",
        f"Main contributor: {main_contributor.get('dimension', 'N/A')} = {main_contributor.get('value', 'N/A')} "
        f"({main_contributor.get('pct_of_scope_deviation', 'N/A')}% of deviation)",
        "",
        f"Check: {evidence.get('volume_price_margin_check', 'N/A')}",
    ]
    if evidence.get("low_sample_warning"):
        lines.append(f"\nCAUTION: {evidence['low_sample_warning']}")
    if llm_summary:
        lines.append("\n--- AI Summary ---")
        lines.append(llm_summary)

    return "\n".join(lines)


def send_alert_email(subject: str, body: str) -> bool:
    """Sends via Gmail SMTP. Requires ALERT_EMAIL_FROM, ALERT_EMAIL_APP_PASSWORD,
    ALERT_EMAIL_TO in .env."""
    sender = os.environ.get("ALERT_EMAIL_FROM")
    password = os.environ.get("ALERT_EMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL_TO")

    if not all([sender, password, recipient]):
        raise EnvironmentError(
            "Missing ALERT_EMAIL_FROM / ALERT_EMAIL_APP_PASSWORD / ALERT_EMAIL_TO in .env"
        )

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)

    return True


def maybe_alert(evidence: dict, llm_summary: str = None, force: bool = False) -> dict:
    severity_result = classify_severity(
        evidence["business_impact"], low_sample_warning=None,
    )

    if severity_result.severity not in (Severity.HIGH, Severity.CRITICAL) and not force:
        return {"sent": False, "reason": f"severity {severity_result.severity.value} below alert threshold",
                "severity": severity_result.severity.value}

    seed = evidence.get("seed_scope") or {}
    key = _cooldown_key(evidence["metric"], evidence["window_start"], evidence["window_end"],
                         seed.get("region"), seed.get("category"))
    state = _load_cooldown_state()

    if _is_in_cooldown(key, state) and not force:
        return {"sent": False, "reason": "in cooldown period (already alerted recently)",
                "severity": severity_result.severity.value}

    subject = f"[{severity_result.severity.value}] Anomaly detected: {evidence['metric']} {evidence['window_start']} to {evidence['window_end']}"
    body = build_alert_email(evidence, severity_result.severity, llm_summary)

    send_alert_email(subject, body)

    state[key] = datetime.now().isoformat()
    _save_cooldown_state(state)

    return {"sent": True, "severity": severity_result.severity.value, "reasoning": severity_result.reasoning}


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
    from evidence_packager import package_evidence
    import pandas as pd

    df = pd.read_csv("data/processed/transactions_with_anomalies.csv", parse_dates=["order_date"])
    evidence = package_evidence(df, metric="sales", window_start="2022-06-01", window_end="2022-06-14")

    result = maybe_alert(evidence.to_dict(), llm_summary="(test run -- no LLM summary attached)")
    print(json.dumps(result, indent=2))

