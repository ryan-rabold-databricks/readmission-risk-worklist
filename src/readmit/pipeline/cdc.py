"""Register a bronze-to-silver AUTO CDC (SCD Type 1) flow for one EHR entity."""

from __future__ import annotations

from pyspark import pipelines as dp
from pyspark.sql import Column, SparkSession
from pyspark.sql import functions as F

from readmit.pipeline.audit import AUDIT_SCHEMA, source_audit_columns
from readmit.pipeline.quality_rules import failed_rules
from readmit.pipeline.settings import PipelineSettings


def register_scd1_table(
    spark: SparkSession,
    settings: PipelineSettings,
    *,
    entity: str,
    target: str,
    keys: list[str],
    columns: list[Column],
    schema: str,
    comment: str,
    cluster_by: list[str],
) -> None:
    """Valid rows of ehr_bronze.<entity>_raw -> latest version per key in ``target``.

    ``schema`` lists the business columns and constraints; audit columns are appended.
    Changes apply in record_updated_ts order, so late or re-sent records cannot
    overwrite newer ones.
    """
    view = f"{target.rsplit('.', 1)[-1]}_changes"

    @dp.temporary_view(name=view)
    def changes():
        return (
            spark.readStream.table(f"{entity}_raw")
            .filter(F.size(failed_rules(entity)) == 0)
            .select(*columns, *source_audit_columns(settings.pipeline_name), "record_updated_ts")
        )

    business, _, constraints = schema.partition("CONSTRAINT")
    full_schema = f"{business.rstrip().rstrip(',')}, {AUDIT_SCHEMA}"
    if constraints:
        full_schema += f", CONSTRAINT{constraints}"
    dp.create_streaming_table(name=target, comment=comment, schema=full_schema, cluster_by=cluster_by)
    dp.create_auto_cdc_flow(
        target=target,
        source=view,
        keys=keys,
        sequence_by="record_updated_ts",
        except_column_list=["record_updated_ts"],
        stored_as_scd_type=1,
    )
