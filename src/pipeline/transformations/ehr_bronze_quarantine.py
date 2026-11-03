"""ehr_bronze.quarantine_raw: every bronze row that fails a data-quality rule.

One table for all entities, with the failed rule names and the original record as
JSON, so nothing is dropped silently and failures can be triaged by rule.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline.quality_rules import RULES, failed_rules

dp.create_streaming_table(
    name="quarantine_raw",
    comment="EHR extract rows that failed bronze data-quality rules (one row per failing record).",
    cluster_by=["entity", "extract_date"],
)


def _register_quarantine_flow(entity: str) -> None:
    @dp.append_flow(target="quarantine_raw", name=f"quarantine_{entity}")
    def flow():
        raw = spark.readStream.table(f"{entity}_raw")  # noqa: F821
        record_cols = [c for c in raw.columns if not c.startswith("_source") and c != "_ingested_at"]
        return (
            raw.withColumn("failed_rules", failed_rules(entity))
            .filter(F.size("failed_rules") > 0)
            .select(
                F.lit(entity).alias("entity"),
                "failed_rules",
                F.to_json(F.struct(*record_cols)).alias("record_json"),
                "extract_date",
                "_source_file",
                "_ingested_at",
                F.current_timestamp().alias("quarantined_at"),
            )
        )


for _entity in RULES:
    _register_quarantine_flow(_entity)
