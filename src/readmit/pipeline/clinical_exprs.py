"""Column expressions generated from readmit.common.clinical_codes."""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F

from readmit.common.clinical_codes import CHARLSON_CATEGORIES, CONDITION_GROUP_PREFIXES

# Higher-severity category -> the milder category it supersedes (Charlson hierarchy).
CHARLSON_HIERARCHY: dict[str, str] = {
    "diabetes_complicated": "diabetes_uncomplicated",
    "moderate_severe_liver": "mild_liver",
    "metastatic_tumor": "malignancy",
}


def prefixes_longest_first(prefixes) -> list[str]:
    return sorted(prefixes, key=lambda p: (-len(p), p))


def _starts_with_any(code: Column, prefixes) -> Column:
    cond = None
    for p in prefixes:
        c = code.startswith(p)
        cond = c if cond is None else cond | c
    return cond


def condition_group(code: Column) -> Column:
    """Condition group by longest matching ICD-10 prefix; NULL when unmapped."""
    expr = None
    for prefix in prefixes_longest_first(CONDITION_GROUP_PREFIXES):
        cond = code.startswith(prefix)
        group = F.lit(CONDITION_GROUP_PREFIXES[prefix])
        expr = F.when(cond, group) if expr is None else expr.when(cond, group)
    return expr.otherwise(F.lit(None).cast("string"))


def charlson_flag_aggs(code: Column) -> list[Column]:
    """One MAX(0/1) aggregate per Charlson category, aliased cci_<category>."""
    return [
        F.max(F.when(_starts_with_any(code, prefixes), 1).otherwise(0)).alias(f"cci_{name}")
        for name, (_, prefixes, _) in CHARLSON_CATEGORIES.items()
    ]


def charlson_index() -> Column:
    """Weighted Charlson index from cci_<category> flags, applying the hierarchy."""
    superseded = {mild: severe for severe, mild in CHARLSON_HIERARCHY.items()}
    total = F.lit(0)
    for name, (_, _, weight) in CHARLSON_CATEGORIES.items():
        flag = F.col(f"cci_{name}")
        if name in superseded:
            flag = F.when(F.col(f"cci_{superseded[name]}") == 1, 0).otherwise(flag)
        total = total + flag * F.lit(weight)
    return total.cast("int")
