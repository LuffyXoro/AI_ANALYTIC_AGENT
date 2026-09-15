from dataclasses import dataclass
from enum import Enum

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass
class SeverityResult:
    severity: Severity
    reasoning: str

# Thresholds -- documented and adjustable
MAGNITUDE_THRESHOLDS = {"critical": 40.0, "high": 20.0, "medium": 10.0}  # |pct_change| in %
IMPACT_THRESHOLDS = {"critical": 1_000_000, "high": 200_000, "medium": 50_000}  # absolute shortfall, currency units
LOW_CONFIDENCE_CAP = Severity.MEDIUM  # low-sample anomaly can never be rated above this


def classify_severity(business_impact: dict, low_sample_warning: str = None) -> SeverityResult:
    pct = abs(business_impact.get("pct_change") or 0)
    shortfall = abs(business_impact.get("shortfall") or 0)

    # Score on magnitude
    if pct >= MAGNITUDE_THRESHOLDS["critical"]:
        magnitude_severity = Severity.CRITICAL
    elif pct >= MAGNITUDE_THRESHOLDS["high"]:
        magnitude_severity = Severity.HIGH
    elif pct >= MAGNITUDE_THRESHOLDS["medium"]:
        magnitude_severity = Severity.MEDIUM
    else:
        magnitude_severity = Severity.LOW

    # Score on absolute business impact
    if shortfall >= IMPACT_THRESHOLDS["critical"]:
        impact_severity = Severity.CRITICAL
    elif shortfall >= IMPACT_THRESHOLDS["high"]:
        impact_severity = Severity.HIGH
    elif shortfall >= IMPACT_THRESHOLDS["medium"]:
        impact_severity = Severity.MEDIUM
    else:
        impact_severity = Severity.LOW

    order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    combined = max(magnitude_severity, impact_severity, key=order.index)

    reasoning = f"Magnitude {pct:.1f}% -> {magnitude_severity.value}; absolute impact {shortfall:,.0f} -> {impact_severity.value}; combined = {combined.value}"

    if low_sample_warning and order.index(combined) > order.index(LOW_CONFIDENCE_CAP):
        reasoning += f"; capped to {LOW_CONFIDENCE_CAP.value} due to low sample size ({low_sample_warning})"
        combined = LOW_CONFIDENCE_CAP

    return SeverityResult(severity=combined, reasoning=reasoning)


if __name__ == "__main__":
    test_cases = [
        ("Scenario 1 (company-wide)", {"pct_change": -12.9, "shortfall": 2540809.0}, None),
        ("Scenario 1 (South-scoped)", {"pct_change": -44.87, "shortfall": 2212032.22}, None),
        ("Scenario 2 (North+Furniture)", {"pct_change": -57.65, "shortfall": 89203.13},
         "CAUTION: only 29 orders in the scope"),
        ("Scenario 3 (company-wide, quiet)", {"pct_change": -0.69, "shortfall": 135563.0}, None),
    ]
    for label, impact, warning in test_cases:
        result = classify_severity(impact, low_sample_warning=warning)
        print(f"{label}: {result.severity.value}")
        print(f"  {result.reasoning}\n")