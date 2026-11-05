# Phase 3: first-model AUC gate failure and simulator signal fix

## Finding

The first model (as of 2026-05-01, generator v2 data) reached test AUC 0.651 against the
approved first-model gate of 0.68, with good calibration (slope 1.066; decile observed
rate 6.9% to 30.0%). Model version 2, `promoted=false`.

## Experiment: features and history are not the constraint

`feature_experiment.py` (serverless one-off run 42482405944796, not registered):

| as_of | train_rows | features | test_auc | brier | calibration_slope |
|---|---|---|---|---|---|
| 2026-05-01 | 11692 | current | 0.6510 | 0.12415 | 1.066 |
| 2026-05-01 | 11692 | +facility | 0.6564 | 0.12384 | 1.097 |
| 2026-05-01 | 11692 | +facility+payer+month | 0.6562 | 0.12384 | 1.166 |
| 2026-08-01 | 23539 | current | 0.6491 | 0.11296 | 0.984 |
| 2026-08-01 | 23539 | +facility | 0.6518 | 0.11283 | 1.015 |
| 2026-08-01 | 23539 | +facility+payer+month | 0.6539 | 0.11271 | 1.053 |
| 2026-11-01 | 34185 | current | 0.6476 | 0.11759 | 0.939 |
| 2026-11-01 | 34185 | +facility | 0.6474 | 0.11756 | 0.923 |
| 2026-11-01 | 34185 | +facility+payer+month | 0.6496 | 0.11741 | 0.958 |

AUC stayed near 0.65 regardless of training history or extra features: the synthetic
data's observable signal was below the approved Phase 1 target (AUC 0.72-0.78).

## Fix (author decision: fix the simulator to plan, keep the 0.68 gate)

`simulator_auc_estimator.py` estimates model AUC directly from the generated universe
(gold-equivalent features and label, time split train < 2026-07-01, test >= 2026-08-01).
It reproduced the real model (0.645 vs 0.651) and was used to tune:

| within-tier frailty SD | comorbidity frailty scale | readmit frailty coef | intercept | est. AUC | readmit rate | Riverbend | HF no / with 7d follow-up |
|---|---|---|---|---|---|---|---|
| 0.8 | 1.0 | 0.45 | -2.88 | 0.645 | 16.1% | 21.4% | 26.7% / 14.5% |
| 0.5 | 1.4 | 0.85 | -3.10 | 0.669 | 15.9% | 20.8% | 26.1% / 15.0% |
| 0.35 | 1.8 | 1.2 | -3.40 | 0.696 | 15.2% | 19.6% | 24.8% / 14.9% |
| 0.35 | 2.0 | 1.5 | -3.60 | 0.717 | 15.4% | 19.6% | 25.2% / 15.6% |
| 0.25 | 2.2 | 1.6 | -3.70 | 0.727 | 15.1% | 19.2% | 24.6% / 15.4% |
| 0.25 | 2.2 | 1.8 | -3.55 | 0.740 | 17.0% | 22.2% | 27.5% / 17.6% |
| 0.25 | 2.4 | 2.0 | -3.65 | 0.758 | 17.4% | 22.4% | 27.8% / 18.6% |
| **0.25** | **2.4** | **2.0** | **-3.75** | **0.757** | **16.8%** | **21.7%** | **27.0% / 17.9%** |

Rows from the 6th onward use a Riverbend readmission effect of 0.75 (was 0.60). The bold
row is generator v3. Patient frailty now shows up in prior utilization and coded
comorbidities, as it does in real EHR data.
