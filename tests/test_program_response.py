"""Simulator v4 program response, on a tiny local Spark frame."""

from datetime import datetime

import pytest

pyspark = pytest.importorskip("pyspark")


@pytest.fixture(scope="module")
def spark():
    import os

    from pyspark.sql import SparkSession

    if os.environ.get("READMIT_REMOTE_SPARK") == "1":  # Databricks Connect serverless
        from readmit.common.spark import get_spark

        yield get_spark()
        return
    try:
        s = SparkSession.builder.master("local[1]").config("spark.sql.session.timeZone", "UTC").getOrCreate()
    except Exception as e:  # no local JVM
        pytest.skip(f"local Spark unavailable: {e}")
    yield s


def _index(spark, n=4000):
    from pyspark.sql import functions as F

    from readmit.simulator.config import SimulatorConfig
    from readmit.simulator.generate import _with_readmission
    from readmit.simulator.random_exprs import HashRng

    cfg = SimulatorConfig(history_start=datetime(2026, 5, 1).date(), run_date=datetime(2026, 7, 1).date())
    rng = HashRng(cfg.seed)
    df = (spark.range(n).select(
        F.concat(F.lit("IP260601"), F.lpad(F.col("id").cast("string"), 4, "0")).alias("encounter_number"),
        F.lit("FAC-LMC").alias("facility_id"),
        F.when(F.col("id") % 3 == 0, "heart_failure").otherwise("copd").alias("condition_group"),
        F.lit(1.2).alias("frailty"), F.lit(5).alias("los_days"), F.lit(True).alias("emergent"),
        F.lit("HOME").alias("discharge_disposition"), F.lit("MEDICARE").alias("primary_payer"),
        F.lit(False).alias("is_winter"), F.lit(False).alias("followup_7d_planned"), F.lit(20).alias("followup_offset_days"),
        F.to_timestamp(F.lit("2026-06-01 14:00:00")).alias("discharge_ts")))
    return cfg, rng, _with_readmission(df, cfg, rng)


def test_no_reach_changes_nothing(spark):
    from readmit.simulator.generate import _with_program_response

    cfg, rng, idx = _index(spark)
    out = _with_program_response(idx, None, cfg, rng)
    assert out.filter("readmit_prevented").count() == 0
    assert out.filter("planned_readmit").count() == idx.filter("planned_readmit").count()


def test_reach_prevents_but_never_adds_and_respects_timing(spark):
    from pyspark.sql import functions as F

    from readmit.simulator.generate import _with_program_response

    cfg, rng, idx = _index(spark)
    reach = idx.select(F.sha2(F.sha2("encounter_number", 256), 256).alias("worklist_item_id"),
                       F.to_timestamp(F.lit("2026-06-02 13:00:00")).alias("reach_ts"))
    out = _with_program_response(idx, reach, cfg, rng)
    before = {r.encounter_number for r in idx.filter("planned_readmit").collect()}
    after = {r.encounter_number for r in out.filter("planned_readmit").collect()}
    assert after < before  # strictly fewer readmissions, none added
    # Readmissions admitted before the reach are never prevented.
    early = out.filter(F.col("readmit_prevented") & (F.col("readmit_admit_ts").isNotNull()))
    assert early.count() == 0
    booked = out.filter("cm_followup_booked")
    assert 0.55 < booked.count() / out.count() < 0.75
    assert booked.filter(F.col("cm_scheduled_ts") <= F.col("cm_booked_ts")).count() == 0
