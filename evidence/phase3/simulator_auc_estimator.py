"""Dev-only: estimate model AUC straight from the simulator universe (no landing).

Features mirror gold discharge_features (prior inpatient 12m, ED 6m, Charlson-style
comorbidity weight, LOS, emergent, condition, disposition, follow-up booked within 7d,
age); label mirrors gold (non-elective inpatient admit within 30 days, hospice excluded).
"""
import sys
from datetime import date

import numpy as np
from pyspark.sql import functions as F
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from readmit.common.clinical_codes import CHARLSON_CATEGORIES
from readmit.common.spark import get_spark
from readmit.simulator.config import SimulatorConfig
from readmit.simulator.generate import build_universe
from readmit.simulator.summary import story_report

spark = get_spark()
cfg = SimulatorConfig(history_start=date(2024, 11, 1), run_date=date(2026, 11, 4))
u = build_universe(spark, cfg)
ip = u.inpatient
weights = {code: w for code, _, w in CHARLSON_CATEGORIES.values()}
wmap = F.create_map(*[x for k, v in weights.items() for x in (F.lit(k), F.lit(v))])

idx = ip.filter("discharge_disposition != 'HOSPICE'").select(
    "encounter_number", "patient_idx", "admit_ts", "discharge_ts", "los_days", "emergent", "condition_group",
    "discharge_disposition", "age",
    (F.col("followup_scheduled") & (F.col("followup_offset_days") <= 7)).alias("fu_booked"),
    F.aggregate(F.transform("comorbid_codes", lambda c: F.coalesce(F.element_at(wmap, c), F.lit(0))), F.lit(0), lambda a, b: a + b).alias("cci"),
)
allenc = ip.select("patient_idx", F.col("admit_ts").alias("o_admit"), F.lit("IP").alias("t"), F.col("emergent").alias("o_emerg")).unionByName(
    u.extracts["encounter"].limit(0).select(F.lit(0).cast("long").alias("patient_idx"), F.lit(None).cast("timestamp").alias("o_admit"), F.lit("x").alias("t"), F.lit(True).alias("o_emerg")))
ed = spark.createDataFrame([], "patient_idx long, o_admit timestamp, t string, o_emerg boolean")
# ED visits are not exposed on Universe; recompute counts from encounter records keyed by mrn is costly, so
# use the inpatient-only history plus ED via the 'encounter' extract joined back on mrn.
enc = u.extracts["encounter"].filter("mrn IS NOT NULL AND discharge_ts IS NOT NULL")
mrn_map = ip.select("patient_idx", "mrn").distinct()
ed = enc.filter("encounter_type = 'ED'").join(mrn_map, "mrn").select("patient_idx", F.col("admit_ts").alias("o_admit"), F.lit("ED").alias("t"), F.lit(True).alias("o_emerg")).distinct()
hist = allenc.unionByName(ed)
j = idx.join(hist.withColumnRenamed("patient_idx", "p2"), (F.col("patient_idx") == F.col("p2")), "left")
feat = j.groupBy("encounter_number").agg(
    F.sum(F.when((F.col("t") == "IP") & (F.col("o_admit") < F.col("admit_ts")) & (F.col("o_admit") >= F.col("admit_ts") - F.expr("INTERVAL 365 DAYS")), 1).otherwise(0)).alias("ip12"),
    F.sum(F.when((F.col("t") == "ED") & (F.col("o_admit") < F.col("admit_ts")) & (F.col("o_admit") >= F.col("admit_ts") - F.expr("INTERVAL 182 DAYS")), 1).otherwise(0)).alias("ed6"),
    F.max(F.when((F.col("t") == "IP") & F.col("o_emerg") & (F.col("o_admit") > F.col("discharge_ts")) & (F.col("o_admit") <= F.col("discharge_ts") + F.expr("INTERVAL 30 DAYS")), 1).otherwise(0)).alias("y"),
)
df = idx.join(feat, "encounter_number").filter(F.to_date("discharge_ts").between(F.lit("2025-11-01"), F.lit("2026-10-04"))).withColumn("d", F.to_date("discharge_ts")).toPandas()
X = df[["ip12", "ed6", "cci", "los_days", "age"]].astype(float)
X["emergent"] = df["emergent"].astype(int); X["fu"] = df["fu_booked"].astype(int)
for c in ["condition_group", "discharge_disposition"]:
    X = X.join(df[c].astype("category").cat.codes.rename(c))
train, test = df["d"] < date(2026, 7, 1), df["d"] >= date(2026, 8, 1)
m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, categorical_features=[X.columns.get_loc("condition_group"), X.columns.get_loc("discharge_disposition")]).fit(X[train], df["y"][train])
p = m.predict_proba(X[test])[:, 1]
print(f"ESTIMATE rows_train={train.sum()} rows_test={test.sum()} label_rate={df['y'].mean():.3f} test_auc={roc_auc_score(df['y'][test], p):.4f}")
print(story_report(u.inpatient, cfg.run_date, 15000))
