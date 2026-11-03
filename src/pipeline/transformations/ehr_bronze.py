"""ehr_bronze.<entity>_raw: append-only Auto Loader ingestion of the EHR extracts.

Every record is kept exactly as received plus ingestion metadata. The data-quality
rules run here as warn-only expectations, so their pass/fail counts appear in the
pipeline event log; failing rows are routed to quarantine_raw, not to silver.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from readmit.pipeline.quality_rules import RULES
from readmit.pipeline.settings import load_settings
from readmit.pipeline.source_schemas import SOURCE_SCHEMAS

settings = load_settings(spark)  # noqa: F821 - spark is provided by the pipeline runtime


def _register_raw_table(entity: str) -> None:
    @dp.table(
        name=f"{entity}_raw",
        comment=f"Raw EHR {entity} extract records, append-only, as landed in ehr_raw.ehr_landing.",
        cluster_by=["extract_date"],
    )
    @dp.expect_all(RULES[entity])
    def raw():
        return (
            spark.readStream.format("cloudFiles")  # noqa: F821
            .option("cloudFiles.format", "json")
            .option("cloudFiles.partitionColumns", "extract_date")
            .option("rescuedDataColumn", "_rescued_data")
            .schema(SOURCE_SCHEMAS[entity])
            .load(f"{settings.landing_path}/{entity}")
            .select(
                "*",
                F.col("_metadata.file_path").alias("_source_file"),
                F.col("_metadata.file_modification_time").alias("_source_file_modified_at"),
                F.current_timestamp().alias("_ingested_at"),
            )
        )


for _entity in SOURCE_SCHEMAS:
    _register_raw_table(_entity)
