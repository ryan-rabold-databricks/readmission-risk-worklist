"""Deterministic, hash-based random Column expressions.

Every draw is a pure function of (seed, salt, key columns), so regenerating the
universe always yields identical rows regardless of partitioning or recomputation.
That is what makes the simulator idempotent without storing any state.
"""

from __future__ import annotations

import math
from functools import reduce
from typing import Sequence

from pyspark.sql import Column
from pyspark.sql import functions as F

_DENOM = 1_000_000_007


class HashRng:
    def __init__(self, seed: int) -> None:
        self.seed = seed

    def u(self, salt: str, *keys: Column | str) -> Column:
        """Uniform draw in the open interval (0, 1)."""
        h = F.xxhash64(F.lit(self.seed), F.lit(salt), *keys)
        return (F.pmod(h, F.lit(_DENOM)).cast("double") + F.lit(0.5)) / F.lit(float(_DENOM))

    def normal(self, salt: str, *keys: Column | str) -> Column:
        """Standard normal draw (Box-Muller)."""
        u1 = self.u(f"{salt}:n1", *keys)
        u2 = self.u(f"{salt}:n2", *keys)
        return F.sqrt(F.lit(-2.0) * F.log(u1)) * F.cos(F.lit(2.0 * math.pi) * u2)

    def pick(self, salt: str, options: Sequence[str], *keys: Column | str) -> Column:
        """Uniform pick from a literal list."""
        idx = F.floor(self.u(salt, *keys) * F.lit(len(options))).cast("int") + F.lit(1)
        return F.element_at(F.array(*[F.lit(o) for o in options]), idx)


def weighted_choice(u: Column, weights: Sequence[tuple[str, Column | float]]) -> Column:
    """Pick a label using per-row weights (literal or Column) and a uniform draw."""
    cols = [(label, w if isinstance(w, Column) else F.lit(float(w))) for label, w in weights]
    total = reduce(lambda a, b: a + b, [w for _, w in cols])
    expr = None
    running = None
    for label, w in cols[:-1]:
        running = w if running is None else running + w
        cond = u < running / total
        expr = F.when(cond, F.lit(label)) if expr is None else expr.when(cond, F.lit(label))
    last = F.lit(cols[-1][0])
    return last if expr is None else expr.otherwise(last)


def sigmoid(x: Column) -> Column:
    return F.lit(1.0) / (F.lit(1.0) + F.exp(-x))


def literal_map(mapping: dict) -> Column:
    """MAP literal from a Python dict."""
    items = []
    for k, v in mapping.items():
        items += [F.lit(k), v if isinstance(v, Column) else F.lit(v)]
    return F.create_map(*items)


def ts_at(day: Column, seconds: Column) -> Column:
    """Timestamp at ``day`` midnight UTC plus ``seconds``."""
    return F.timestamp_seconds(F.unix_timestamp(day.cast("timestamp")) + seconds.cast("long"))
