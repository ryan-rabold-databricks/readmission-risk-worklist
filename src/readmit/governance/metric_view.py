"""Render the readmission_program_metrics metric view DDL from its committed YAML template.

Metric views have no bundle resource type and no parameters, so the deploy-time values
(catalog, program go-live, assumed cost per readmission) are rendered into the YAML here
and applied by the governance setup job with CREATE OR REPLACE (idempotent).
"""

from __future__ import annotations

import datetime as dt
import re
from importlib import resources

METRIC_VIEW = "readmission_worklist_gold.readmission_program_metrics"
_TEMPLATE = "readmission_program_metrics.yaml"
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def render_yaml(catalog: str, go_live: str, avg_cost: str) -> str:
    """Validate the inputs (they are inlined into SQL) and fill in the template."""
    if not _IDENT.match(catalog):
        raise ValueError(f"catalog must be a plain identifier: {catalog!r}")
    go_live_date = dt.date.fromisoformat(go_live).isoformat()
    cost = float(avg_cost)
    if not cost > 0:
        raise ValueError(f"avg_cost must be positive: {avg_cost!r}")
    cost_text = f"{cost:.0f}" if cost.is_integer() else repr(cost)
    text = resources.files("readmit.governance").joinpath(_TEMPLATE).read_text()
    text = text.replace("__CATALOG__", catalog).replace("__GO_LIVE__", go_live_date).replace("__AVG_COST__", cost_text)
    if "$$" in text or re.search(r"__[A-Z_]+__", text):
        raise ValueError("Unrendered placeholder or $$ in metric view YAML")
    return text


def create_statement(catalog: str, go_live: str, avg_cost: str) -> str:
    body = render_yaml(catalog, go_live, avg_cost)
    return f"CREATE OR REPLACE VIEW {catalog}.{METRIC_VIEW}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{body}$$"
