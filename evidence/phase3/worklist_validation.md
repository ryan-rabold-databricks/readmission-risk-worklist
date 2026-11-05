# Phase 3 validation: scores, worklist, roster, briefs

Run on `fevm-classic-stable` after the program backfill, 2026-11-05T19:22Z.

## Model versions and aliases

Which model version scored which worklist days (monthly retrains; the then-current @champion).

```sql
SELECT model_name, model_version, count(*) scores, min(worklist_date) first_day, max(worklist_date) last_day FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score GROUP BY 1,2 ORDER BY 2
```

```json
[
  {
    "first_day": "2026-05-01",
    "last_day": "2026-05-31",
    "model_name": "rtr_demo_catalog.readmission_worklist_gold.readmission_risk",
    "model_version": "3",
    "scores": "4742"
  },
  {
    "first_day": "2026-06-01",
    "last_day": "2026-06-30",
    "model_name": "rtr_demo_catalog.readmission_worklist_gold.readmission_risk",
    "model_version": "4",
    "scores": "4385"
  },
  {
    "first_day": "2026-07-01",
    "last_day": "2026-07-31",
    "model_name": "rtr_demo_catalog.readmission_worklist_gold.readmission_risk",
    "model_version": "5",
    "scores": "4459"
  },
  {
    "first_day": "2026-08-01",
    "last_day": "2026-09-30",
    "model_name": "rtr_demo_catalog.readmission_worklist_gold.readmission_risk",
    "model_version": "6",
    "scores": "8961"
  },
  {
    "first_day": "2026-10-01",
    "last_day": "2026-10-31",
    "model_name": "rtr_demo_catalog.readmission_worklist_gold.readmission_risk",
    "model_version": "8",
    "scores": "4865"
  },
  {
    "first_day": "2026-11-01",
    "last_day": "2026-11-05",
    "model_name": "rtr_demo_catalog.readmission_worklist_gold.readmission_risk",
    "model_version": "9",
    "scores": "736"
  }
]
```

## Coverage: every worklist day since go-live is scored and built

```sql
SELECT count(DISTINCT s.worklist_date) scored_days, (SELECT count(DISTINCT worklist_date) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist) worklist_days, min(s.worklist_date) first_day, max(s.worklist_date) last_day, datediff(max(s.worklist_date), min(s.worklist_date)) + 1 expected_days FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score s
```

```json
[
  {
    "expected_days": "189",
    "first_day": "2026-05-01",
    "last_day": "2026-11-05",
    "scored_days": "189",
    "worklist_days": "189"
  }
]
```

## Idempotency: one score per discharge per model version and run, one worklist item per discharge

```sql
SELECT (SELECT count(*) - count(DISTINCT score_id) FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score) duplicate_scores, (SELECT count(*) - count(DISTINCT encounter_id) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist) duplicate_worklist_items, (SELECT count(*) - count(DISTINCT roster_id) FROM rtr_demo_catalog.readmission_worklist_gold.care_team_roster) duplicate_roster_rows
```

```json
[
  {
    "duplicate_roster_rows": "0",
    "duplicate_scores": "0",
    "duplicate_worklist_items": "0"
  }
]
```

## Risk tier mix per day (average)

```sql
SELECT risk_tier, round(count(*) / count(DISTINCT worklist_date), 1) avg_per_day, round(avg(risk_score), 3) avg_score FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score GROUP BY 1 ORDER BY 3 DESC
```

```json
[
  {
    "avg_per_day": "26.5",
    "avg_score": "0.396",
    "risk_tier": "HIGH"
  },
  {
    "avg_per_day": "20.1",
    "avg_score": "0.237",
    "risk_tier": "MEDIUM"
  },
  {
    "avg_per_day": "102.4",
    "avg_score": "0.086",
    "risk_tier": "LOW"
  }
]
```

## Capacity respected: assigned items per care manager per day never exceed capacity

```sql
SELECT w.assigned_care_manager, max(n) max_assigned_in_a_day, max(cap) daily_capacity, round(avg(n), 1) avg_assigned FROM (SELECT assigned_care_manager, worklist_date, count(*) n FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist WHERE assignment_status = 'ASSIGNED' GROUP BY 1,2) w JOIN (SELECT DISTINCT care_manager_email, roster_date, daily_capacity cap FROM rtr_demo_catalog.readmission_worklist_gold.care_team_roster) r ON r.care_manager_email = w.assigned_care_manager AND r.roster_date = w.worklist_date GROUP BY 1
```

```json
[
  {
    "assigned_care_manager": "ryan.rabold@databricks.com",
    "avg_assigned": "44.3",
    "daily_capacity": "50",
    "max_assigned_in_a_day": "50"
  }
]
```

## Overflow: items over capacity, and that assignment is highest risk first

Highest risk first: on every day, the lowest assigned score should be at or above the highest overflow score.

```sql
SELECT assignment_status, count(*) items, round(count(*) / count(DISTINCT worklist_date), 1) avg_per_day, round(min(risk_score), 3) min_score, round(max(risk_score), 3) max_score FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist GROUP BY 1
```

```json
[
  {
    "assignment_status": "OVERFLOW",
    "avg_per_day": "6.4",
    "items": "438",
    "max_score": "0.265",
    "min_score": "0.18"
  },
  {
    "assignment_status": "ASSIGNED",
    "avg_per_day": "44.3",
    "items": "8364",
    "max_score": "0.721",
    "min_score": "0.18"
  }
]
```

## Highest-risk-first check (days where an overflow item outranks an assigned one)

```sql
SELECT count(*) violating_days FROM (SELECT worklist_date, min(CASE WHEN assignment_status = 'ASSIGNED' THEN risk_score END) min_assigned, max(CASE WHEN assignment_status = 'OVERFLOW' THEN risk_score END) max_overflow FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist GROUP BY 1) WHERE max_overflow > min_assigned
```

```json
[
  {
    "violating_days": "0"
  }
]
```

## Outreach briefs: coverage by worklist day (latest 14 days only)

```sql
SELECT worklist_date, count(*) items, count_if(length(trim(outreach_brief)) >= 80) with_brief, round(avg(length(outreach_brief))) avg_brief_chars FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist WHERE worklist_date >= date_sub((SELECT max(worklist_date) FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist), 16) GROUP BY 1 ORDER BY 1
```

```json
[
  {
    "avg_brief_chars": "",
    "items": "60",
    "with_brief": "0",
    "worklist_date": "2026-10-20"
  },
  {
    "avg_brief_chars": "",
    "items": "44",
    "with_brief": "0",
    "worklist_date": "2026-10-21"
  },
  {
    "avg_brief_chars": "",
    "items": "54",
    "with_brief": "0",
    "worklist_date": "2026-10-22"
  },
  {
    "avg_brief_chars": "455.0",
    "items": "48",
    "with_brief": "48",
    "worklist_date": "2026-10-23"
  },
  {
    "avg_brief_chars": "465.0",
    "items": "53",
    "with_brief": "53",
    "worklist_date": "2026-10-24"
  },
  {
    "avg_brief_chars": "465.0",
    "items": "35",
    "with_brief": "35",
    "worklist_date": "2026-10-25"
  },
  {
    "avg_brief_chars": "462.0",
    "items": "42",
    "with_brief": "42",
    "worklist_date": "2026-10-26"
  },
  {
    "avg_brief_chars": "458.0",
    "items": "63",
    "with_brief": "63",
    "worklist_date": "2026-10-27"
  },
  {
    "avg_brief_chars": "465.0",
    "items": "52",
    "with_brief": "52",
    "worklist_date": "2026-10-28"
  },
  {
    "avg_brief_chars": "466.0",
    "items": "58",
    "with_brief": "58",
    "worklist_date": "2026-10-29"
  },
  {
    "avg_brief_chars": "463.0",
    "items": "42",
    "with_brief": "42",
    "worklist_date": "2026-10-30"
  },
  {
    "avg_brief_chars": "457.0",
    "items": "52",
    "with_brief": "52",
    "worklist_date": "2026-10-31"
  },
  {
    "avg_brief_chars": "463.0",
    "items": "40",
    "with_brief": "40",
    "worklist_date": "2026-11-01"
  },
  {
    "avg_brief_chars": "461.0",
    "items": "51",
    "with_brief": "51",
    "worklist_date": "2026-11-02"
  },
  {
    "avg_brief_chars": "456.0",
    "items": "50",
    "with_brief": "50",
    "worklist_date": "2026-11-03"
  },
  {
    "avg_brief_chars": "464.0",
    "items": "59",
    "with_brief": "59",
    "worklist_date": "2026-11-04"
  },
  {
    "avg_brief_chars": "455.0",
    "items": "46",
    "with_brief": "46",
    "worklist_date": "2026-11-05"
  }
]
```

## Sample worklist items with drivers and brief (synthetic data)

```sql
SELECT worklist_date, facility_id, risk_tier, round(risk_score, 3) risk_score, assignment_status, top_drivers, due_at, outreach_brief FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist WHERE length(trim(outreach_brief)) >= 80 ORDER BY risk_score DESC LIMIT 3
```

```json
[
  {
    "assignment_status": "ASSIGNED",
    "due_at": "2026-11-04T12:00:00.000Z",
    "facility_id": "FAC-SVH",
    "outreach_brief": "- **Why at risk:** HIGH tier (62% predicted 30-day readmission) after heart failure admission; Charlson index 8, no follow-up booked within 7 days, discharged to a skilled nursing facility.\n- **Ask/check:** Confirm with patient and SNF staff whether follow-up is arranged; check for worsening heart failure symptoms.\n- **Next step:** Book follow-up within 7 days of discharge; complete call by 2026-11-04 12:00 UTC.",
    "risk_score": "0.624",
    "risk_tier": "HIGH",
    "top_drivers": "[\"Comorbidity burden (Charlson index 8)\",\"No follow-up booked within 7 days\",\"Discharged to a skilled nursing facility\"]",
    "worklist_date": "2026-11-03"
  },
  {
    "assignment_status": "ASSIGNED",
    "due_at": "2026-10-29T12:00:00.000Z",
    "facility_id": "FAC-RCH",
    "outreach_brief": "- **Why at risk:** HIGH tier (60% predicted 30-day readmission) after heart failure admission; drivers are comorbidity burden (Charlson 4), 14-day stay, and discharge to a skilled nursing facility.\n- **Ask/check:** Confirm patient is settled at the facility, ask about any worsening heart failure symptoms, and confirm the facility has discharge instructions.\n- **Next step:** Book a follow-up appointment within 7 days (none booked); complete call by 2026-10-29 12:00 UTC.",
    "risk_score": "0.602",
    "risk_tier": "HIGH",
    "top_drivers": "[\"Comorbidity burden (Charlson index 4)\",\"14-day hospital stay\",\"Discharged to a skilled nursing facility\"]",
    "worklist_date": "2026-10-28"
  },
  {
    "assignment_status": "ASSIGNED",
    "due_at": "2026-11-05T12:00:00.000Z",
    "facility_id": "FAC-CCH",
    "outreach_brief": "- **Risk:** HIGH tier (59% predicted 30-day readmission) after heart failure admission; Charlson index 8; 5 inpatient stays in prior 12 months; discharged home without services; no follow-up booked within 7 days.\n- **Ask/check:** Current symptoms (breathlessness, swelling, weight change), understanding of discharge instructions and medications, home support or service needs.\n- **Next step:** Book follow-up within 7 days and consider home services referral; complete call by 2026-11-05 12:00 UTC.",
    "risk_score": "0.593",
    "risk_tier": "HIGH",
    "top_drivers": "[\"Comorbidity burden (Charlson index 8)\",\"5 inpatient stays in the prior 12 months\",\"No follow-up booked within 7 days\"]",
    "worklist_date": "2026-11-04"
  }
]
```

## Brief content check: no PHI identifiers in briefs (patient name or phone never appear in the text)

The prompt never includes name, MRN, or phone; this checks the stored text as well.

```sql
SELECT count(*) briefs, count_if(instr(lower(outreach_brief), lower(split(patient_display_name, ' ')[1])) > 0) contains_last_name, count_if(phone IS NOT NULL AND instr(outreach_brief, substr(phone, -4)) > 0) contains_phone_digits FROM rtr_demo_catalog.readmission_worklist_gold.care_worklist WHERE length(trim(outreach_brief)) >= 80
```

```json
[
  {
    "briefs": "691",
    "contains_last_name": "0",
    "contains_phone_digits": "0"
  }
]
```

## Live calibration: predicted vs. actual by decile for scored discharges with matured labels

```sql
SELECT decile, count(*) n, round(avg(risk_score), 3) mean_predicted, round(avg(CAST(readmit_30d AS INT)), 3) observed_rate FROM (SELECT s.risk_score, f.readmit_30d, ntile(10) OVER (ORDER BY s.risk_score) decile FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score s JOIN rtr_demo_catalog.readmission_worklist_gold.discharge_features f USING (encounter_id) WHERE f.readmit_30d IS NOT NULL) GROUP BY 1 ORDER BY 1
```

```json
[
  {
    "decile": "1",
    "mean_predicted": "0.043",
    "n": "2350",
    "observed_rate": "0.043"
  },
  {
    "decile": "2",
    "mean_predicted": "0.055",
    "n": "2349",
    "observed_rate": "0.054"
  },
  {
    "decile": "3",
    "mean_predicted": "0.067",
    "n": "2349",
    "observed_rate": "0.06"
  },
  {
    "decile": "4",
    "mean_predicted": "0.079",
    "n": "2349",
    "observed_rate": "0.067"
  },
  {
    "decile": "5",
    "mean_predicted": "0.094",
    "n": "2349",
    "observed_rate": "0.078"
  },
  {
    "decile": "6",
    "mean_predicted": "0.118",
    "n": "2349",
    "observed_rate": "0.103"
  },
  {
    "decile": "7",
    "mean_predicted": "0.158",
    "n": "2349",
    "observed_rate": "0.154"
  },
  {
    "decile": "8",
    "mean_predicted": "0.231",
    "n": "2349",
    "observed_rate": "0.212"
  },
  {
    "decile": "9",
    "mean_predicted": "0.325",
    "n": "2349",
    "observed_rate": "0.322"
  },
  {
    "decile": "10",
    "mean_predicted": "0.443",
    "n": "2349",
    "observed_rate": "0.424"
  }
]
```

## Worklist yield: readmission rate by tier for matured outcomes (no outreach effect yet)

```sql
SELECT s.risk_tier, count(*) n, round(avg(CAST(f.readmit_30d AS INT)), 3) readmit_30d_rate FROM rtr_demo_catalog.readmission_worklist_gold.discharge_risk_score s JOIN rtr_demo_catalog.readmission_worklist_gold.discharge_features f USING (encounter_id) WHERE f.readmit_30d IS NOT NULL GROUP BY 1 ORDER BY 3 DESC
```

```json
[
  {
    "n": "4152",
    "readmit_30d_rate": "0.39",
    "risk_tier": "HIGH"
  },
  {
    "n": "3140",
    "readmit_30d_rate": "0.217",
    "risk_tier": "MEDIUM"
  },
  {
    "n": "16199",
    "readmit_30d_rate": "0.078",
    "risk_tier": "LOW"
  }
]
```

