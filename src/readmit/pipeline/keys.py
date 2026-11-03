"""Surrogate keys: SHA-256 of the alternate (natural) key columns, per the ERD."""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F


def hash_key(*cols: str | Column) -> Column:
    parts = [F.col(c) if isinstance(c, str) else c for c in cols]
    return F.sha2(F.concat_ws("|", *[p.cast("string") for p in parts]), 256)
