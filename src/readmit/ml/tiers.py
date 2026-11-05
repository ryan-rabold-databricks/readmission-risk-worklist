"""Risk tier lookup from care_management_silver.risk_tier_policy."""

from __future__ import annotations

import pandas as pd


def tier_for(score: float, policy: pd.DataFrame) -> str:
    for row in policy.itertuples():
        upper_ok = score <= row.max_score if row.max_score >= 1.0 else score < row.max_score
        if row.min_score <= score and upper_ok:
            return row.risk_tier
    raise ValueError(f"No active risk tier covers score {score}")
