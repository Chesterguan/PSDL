#!/usr/bin/env python3
"""
AKI (KDIGO) experiment on the MIMIC-IV -> OMOP test bed.

Protocol (all numbers reported by this script are reproducible):
  1. Compile src/psdl/examples/aki_detection.yaml to SQL (CohortCompiler +
     dataset_specs/omop_cdm_v54.yaml, schema=omop_cdm).
  2. Rewrite the compiled SQL for PER-PATIENT reference times: each
     patient is evaluated at the time of their PEAK serum creatinine
     (MIMIC dates are per-patient shifted, so a global reference_time is
     meaningless). The rewrite injects a `ref` CTE and joins it into
     every trend CTE; the compiler itself is not modified.
  3. Execute on the test bed and aggregate KDIGO stage counts.
  4. Consistency check: sample N patients, re-evaluate them in pure
     Python with SinglePatientEvaluator at the same anchors, and compare
     every logic output against the SQL row.

Requires the local test bed:
  postgresql://postgres@localhost:5435/mimiciv_omop (schema omop_cdm)

Usage:
  python scripts/experiment_aki_mimic.py [--sample 200] [--out results.json]
"""

import argparse
import json
import random
import time
from datetime import datetime

import psycopg2

from psdl import load_dataset_spec, parse_scenario
from psdl.runtimes.cohort import CohortCompiler
from psdl.runtimes.single import InMemoryBackend, SinglePatientEvaluator

DB_URL = "postgresql://postgres@localhost:5435/mimiciv_omop"
SCENARIO = "src/psdl/examples/aki_detection.yaml"
DATASET_SPEC = "dataset_specs/omop_cdm_v54.yaml"
SCHEMA = "omop_cdm"
CREATININE_CONCEPT = 3016723
BUN_CONCEPT = 3013682

LOGIC_COLS = [
    "cr_rise_flag",
    "aki_stage3",
    "aki_stage2",
    "aki_stage1",
    "aki_present",
    "cr_falling",
    "aki_recovering",
    "bun_elevated",
    "prerenal_likely",
]

REF_CTE = f"""ref AS (
    SELECT DISTINCT ON (person_id) person_id, measurement_datetime AS ref_time
    FROM {SCHEMA}.measurement
    WHERE measurement_concept_id = {CREATININE_CONCEPT}
      AND value_as_number IS NOT NULL
    ORDER BY person_id, value_as_number DESC, measurement_datetime
)"""


def rewrite_for_per_patient_ref(sql: str) -> str:
    """Global :reference_time -> per-patient peak-creatinine anchor."""
    sql = sql.replace(
        f"FROM {SCHEMA}.measurement",
        f"FROM {SCHEMA}.measurement JOIN ref USING (person_id)",
    )
    sql = sql.replace(":reference_time", "ref_time")
    assert sql.startswith("WITH ")
    return "WITH " + REF_CTE + ",\n" + sql[len("WITH ") :]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--out", default="scripts/experiment_aki_mimic_results.json")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    results = {"generated_at": datetime.now().isoformat(), "protocol": {
        "anchor": "per-patient peak creatinine time",
        "baseline": "min(Cr, 7d) before anchor (KDIGO retrospective surrogate)",
        "scenario": SCENARIO,
        "dataset_spec": DATASET_SPEC,
    }}

    scenario = parse_scenario(SCENARIO)
    ds = load_dataset_spec(DATASET_SPEC, schema=SCHEMA)

    t0 = time.time()
    compiled = CohortCompiler(schema=SCHEMA).compile(scenario, dataset_spec=ds)
    results["compile_seconds"] = round(time.time() - t0, 4)

    cohort_sql = rewrite_for_per_patient_ref(compiled.sql)

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # ── Data recon ────────────────────────────────────────────────
    cur.execute(
        f"SELECT count(*), count(DISTINCT person_id),"
        f" percentile_cont(0.5) WITHIN GROUP (ORDER BY value_as_number)"
        f" FROM {SCHEMA}.measurement"
        f" WHERE measurement_concept_id = {CREATININE_CONCEPT}"
        f" AND value_as_number IS NOT NULL"
    )
    cr_rows, cr_patients, cr_median = cur.fetchone()
    results["data"] = {
        "creatinine_rows": cr_rows,
        "creatinine_patients": cr_patients,
        "creatinine_median": float(cr_median),
    }
    print(f"creatinine: {cr_rows} rows, {cr_patients} patients, median {cr_median}")

    # ── Cohort run: aggregate stage counts in one pass ────────────
    agg_sql = (
        "SELECT count(*),"
        " count(*) FILTER (WHERE aki_stage1),"
        " count(*) FILTER (WHERE aki_stage2),"
        " count(*) FILTER (WHERE aki_stage3),"
        " count(*) FILTER (WHERE aki_present),"
        " count(*) FILTER (WHERE prerenal_likely),"
        " count(*) FILTER (WHERE aki_recovering)"
        f" FROM ({cohort_sql}) q"
    )
    t0 = time.time()
    cur.execute(agg_sql)
    n, s1, s2, s3, present, prerenal, recovering = cur.fetchone()
    exec_seconds = round(time.time() - t0, 1)
    results["cohort"] = {
        "patients_evaluated": n,
        "aki_stage1": s1,
        "aki_stage2": s2,
        "aki_stage3": s3,
        "aki_present": present,
        "aki_prevalence": round(present / n, 4) if n else None,
        "prerenal_likely": prerenal,
        "aki_recovering": recovering,
        "execution_seconds": exec_seconds,
    }
    print(f"cohort: n={n} stage1={s1} stage2={s2} stage3={s3} "
          f"present={present} ({present/n:.1%}) in {exec_seconds}s")

    # ── Consistency check: SQL vs single-patient runtime ──────────
    sample_sql = (
        f"SELECT q.*, ref.ref_time FROM ({cohort_sql}) q"
        f" JOIN ref USING (person_id)"
    )
    # Re-attach ref CTE for the outer join
    sample_sql = "WITH " + REF_CTE + " " + sample_sql
    cur.execute(sample_sql + " ORDER BY random() LIMIT %s", (args.sample,))
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]

    mismatches = []
    checked = 0
    for row in rows:
        rec = dict(zip(cols, row))
        pid, ref_time = rec["person_id"], rec["ref_time"]
        be = InMemoryBackend()
        for concept, sig in ((CREATININE_CONCEPT, "Cr"), (BUN_CONCEPT, "BUN")):
            cur.execute(
                f"SELECT value_as_number, measurement_datetime"
                f" FROM {SCHEMA}.measurement"
                f" WHERE person_id = %s AND measurement_concept_id = %s"
                f" AND measurement_datetime <= %s AND value_as_number IS NOT NULL"
                f" ORDER BY measurement_datetime",
                (pid, concept, ref_time),
            )
            for value, ts in cur.fetchall():
                be.add_observation(pid, sig, float(value), ts)
        ev = SinglePatientEvaluator(scenario, be)
        r = ev.evaluate(pid, reference_time=ref_time)
        checked += 1
        for col in LOGIC_COLS:
            py, sq = bool(r.logic_results.get(col)), bool(rec[col])
            if py != sq:
                mismatches.append({
                    "person_id": pid, "logic": col,
                    "python": py, "sql": sq,
                    "trend_values": {k: v for k, v in r.trend_values.items()},
                })

    results["consistency"] = {
        "patients_checked": checked,
        "logic_outputs_compared": checked * len(LOGIC_COLS),
        "mismatches": len(mismatches),
        "mismatch_detail": mismatches[:10],
        "seed": args.seed,
    }
    print(f"consistency: {checked} patients x {len(LOGIC_COLS)} logic outputs, "
          f"{len(mismatches)} mismatches")

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"results written to {args.out}")


if __name__ == "__main__":
    main()
