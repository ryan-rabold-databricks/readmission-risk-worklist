"""Pipeline settings read from the SDP pipeline configuration (see the pipeline resource)."""

from __future__ import annotations

from dataclasses import dataclass

from pyspark.sql import SparkSession

from readmit.common.env_guardrail import assert_environment


@dataclass(frozen=True)
class PipelineSettings:
    env: str
    catalog: str
    pipeline_name: str
    landing_path: str
    seeds_path: str

    def table(self, schema: str, name: str) -> str:
        return f"{self.catalog}.{schema}.{name}"


def load_settings(spark: SparkSession) -> PipelineSettings:
    conf = spark.conf
    settings = PipelineSettings(
        env=conf.get("readmit.env"),
        catalog=conf.get("readmit.catalog"),
        pipeline_name=conf.get("readmit.pipeline_name"),
        landing_path=conf.get("readmit.landing_path"),
        seeds_path=conf.get("readmit.seeds_path"),
    )
    assert_environment(settings.env, settings.catalog)
    expected_landing = f"/Volumes/{settings.catalog}/ehr_raw/ehr_landing"
    if settings.landing_path.rstrip("/") != expected_landing:
        raise ValueError(f"landing_path {settings.landing_path} does not match {expected_landing}")
    return settings
