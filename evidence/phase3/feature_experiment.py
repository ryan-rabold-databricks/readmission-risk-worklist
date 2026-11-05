# One-off experiment (not registered): does adding facility, payer, and discharge month
# improve test AUC, and how does AUC change with more training history?
import sys
sys.path.insert(0, "/Workspace/Users/ryan.rabold@databricks.com/.bundle/readmission_worklist/dev/files/src")
from datetime import date
import pandas as pd
from pyspark.sql import SparkSession, functions as F
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier
from readmit.ml import model as M
from readmit.ml.features import FEATURE_COLUMNS, NUMERIC_FEATURES, BOOLEAN_FEATURES, CATEGORICAL_FEATURES, LABEL
from readmit.ml.train import time_split
from readmit.ml.metrics import evaluate

spark = SparkSession.builder.getOrCreate()
C = "rtr_demo_catalog"
base = (spark.table(f"{C}.readmission_worklist_gold.discharge_features")
        .join(spark.table(f"{C}.clinical_silver.patient").select("patient_id", "primary_payer"), "patient_id")
        .withColumn("discharge_month", F.month("discharge_date").cast("string"))
        .filter(F.col("discharge_date") >= F.lit("2025-11-01")))
EXTRA = ["facility_id", "primary_payer", "discharge_month"]

def fit_eval(train, val, test, cats):
    def frame(df):
        X = M.model_frame(df)
        for c in EXTRA:
            if c in cats: X[c] = df[c].astype(str).values
        return X
    pre = ColumnTransformer([("num", "passthrough", NUMERIC_FEATURES),
                             ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), BOOLEAN_FEATURES + CATEGORICAL_FEATURES + cats)])
    Xtr, Xv, Xte = frame(train), frame(val), frame(test)
    pre.fit(Xtr)
    clf = XGBClassifier(**M.XGB_PARAMS).fit(pre.transform(Xtr), train[LABEL].astype(int), eval_set=[(pre.transform(Xv), val[LABEL].astype(int))], verbose=False)
    return evaluate(test[LABEL].astype(int).values, clf.predict_proba(pre.transform(Xte))[:, 1])

print("as_of | train_rows | features | test_auc | brier | calibration_slope")
for as_of in [date(2026, 5, 1), date(2026, 8, 1), date(2026, 11, 1)]:
    df = (base.filter(F.col("label_matured_at") <= F.lit(as_of).cast("timestamp"))
          .select("encounter_id", "discharge_date", *FEATURE_COLUMNS, *EXTRA, LABEL).toPandas()
          .sort_values(["discharge_date", "encounter_id"]).reset_index(drop=True))
    tr, va, te = time_split(df)
    for label, cats in [("current", []), ("+facility", ["facility_id"]), ("+facility+payer+month", EXTRA)]:
        m = fit_eval(tr, va, te, cats)
        print(f"{as_of} | {len(tr)} | {label} | {m.auc:.4f} | {m.brier:.5f} | {m.calibration_slope:.3f}")
