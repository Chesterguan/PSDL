"""
Pre-built Benchmark Scenarios for PSDL.

Provides scenarios of varying complexity for benchmarking.
"""

from typing import Dict, List, Optional

# Benchmark scenarios dictionary
BENCHMARK_SCENARIOS: Dict[str, dict] = {
    # Simple scenario: 2 signals, 1 trend, 1 logic
    "simple_threshold": {
        "scenario": "Benchmark_Simple",
        "version": "0.3.0",
        "description": "Simple threshold detection - baseline benchmark",
        "signals": {
            "HR": {"ref": "heart_rate", "concept_id": 3027018},
        },
        "trends": {
            "hr_current": {"expr": "last(HR)", "type": "float"},
        },
        "logic": {
            "tachycardia": {"when": "hr_current > 100", "severity": "medium"},
        },
    },
    # Medium scenario: 4 signals, 4 trends, 2 logic rules
    "medium_aki": {
        "scenario": "Benchmark_AKI",
        "version": "0.3.0",
        "description": "AKI detection with delta and baseline comparison",
        "signals": {
            "Cr": {"ref": "creatinine", "concept_id": 3016723},
            "K": {"ref": "potassium", "concept_id": 3023103},
        },
        "trends": {
            "cr_current": {"expr": "last(Cr)", "type": "float"},
            "cr_delta_48h": {"expr": "delta(Cr, 48h)", "type": "float"},
            "cr_slope_24h": {"expr": "slope(Cr, 24h)", "type": "float"},
            "k_current": {"expr": "last(K)", "type": "float"},
        },
        "logic": {
            "aki_stage1": {"when": "cr_delta_48h >= 0.3", "severity": "medium"},
            "hyperkalemia": {"when": "k_current > 5.5", "severity": "high"},
        },
    },
    # Complex scenario: 8 signals, 12 trends, 6 logic rules with nested logic
    "complex_sepsis": {
        "scenario": "Benchmark_Sepsis",
        "version": "0.3.0",
        "description": "Sepsis detection with SIRS criteria and organ dysfunction",
        "signals": {
            "HR": {"ref": "heart_rate", "concept_id": 3027018},
            "Temp": {"ref": "temperature", "concept_id": 3020891},
            "Resp": {"ref": "respiratory_rate", "concept_id": 3024171},
            "WBC": {"ref": "wbc", "concept_id": 3000905},
            "Lactate": {"ref": "lactate", "concept_id": 3047181},
            "MAP": {"ref": "mean_arterial_pressure", "concept_id": 3027598},
            "Cr": {"ref": "creatinine", "concept_id": 3016723},
            "SpO2": {"ref": "spo2", "concept_id": 3016502},
        },
        "trends": {
            "hr_current": {"expr": "last(HR)", "type": "float"},
            "hr_delta_6h": {"expr": "delta(HR, 6h)", "type": "float"},
            "temp_current": {"expr": "last(Temp)", "type": "float"},
            "resp_current": {"expr": "last(Resp)", "type": "float"},
            "wbc_current": {"expr": "last(WBC)", "type": "float"},
            "lactate_current": {"expr": "last(Lactate)", "type": "float"},
            "lactate_delta_6h": {"expr": "delta(Lactate, 6h)", "type": "float"},
            "map_current": {"expr": "last(MAP)", "type": "float"},
            "cr_current": {"expr": "last(Cr)", "type": "float"},
            "cr_delta_48h": {"expr": "delta(Cr, 48h)", "type": "float"},
            "spo2_current": {"expr": "last(SpO2)", "type": "float"},
            "spo2_min_1h": {"expr": "min(SpO2, 1h)", "type": "float"},
        },
        "logic": {
            "hr_elevated": {"when": "hr_current > 90", "severity": "low"},
            "temp_abnormal": {
                "when": "temp_current > 38.3 OR temp_current < 36",
                "severity": "low",
            },
            "resp_elevated": {"when": "resp_current > 22", "severity": "low"},
            "wbc_abnormal": {
                "when": "wbc_current > 12 OR wbc_current < 4",
                "severity": "low",
            },
            "sirs_criteria": {
                "when": "(hr_elevated AND temp_abnormal) OR (hr_elevated AND resp_elevated) OR (temp_abnormal AND resp_elevated)",
                "severity": "medium",
            },
            "organ_dysfunction": {
                "when": "map_current < 65 OR cr_delta_48h >= 0.3 OR spo2_current < 90",
                "severity": "high",
            },
            "lactate_elevated": {"when": "lactate_current > 2.0", "severity": "medium"},
            "sepsis_suspected": {
                "when": "sirs_criteria AND (lactate_elevated OR organ_dysfunction)",
                "severity": "critical",
            },
        },
    },
    # Very complex scenario: 15 signals, 25 trends, 15 logic rules
    "very_complex_icu": {
        "scenario": "Benchmark_ICU_Deterioration",
        "version": "0.3.0",
        "description": "Comprehensive ICU deterioration detection",
        "signals": {
            "HR": {"ref": "heart_rate", "concept_id": 3027018},
            "SBP": {"ref": "systolic_bp", "concept_id": 3004249},
            "DBP": {"ref": "diastolic_bp", "concept_id": 3012888},
            "MAP": {"ref": "mean_arterial_pressure", "concept_id": 3027598},
            "Temp": {"ref": "temperature", "concept_id": 3020891},
            "Resp": {"ref": "respiratory_rate", "concept_id": 3024171},
            "SpO2": {"ref": "spo2", "concept_id": 3016502},
            "Cr": {"ref": "creatinine", "concept_id": 3016723},
            "K": {"ref": "potassium", "concept_id": 3023103},
            "Na": {"ref": "sodium", "concept_id": 3019550},
            "Lactate": {"ref": "lactate", "concept_id": 3047181},
            "pH": {"ref": "blood_ph", "concept_id": 3019977},
            "Hgb": {"ref": "hemoglobin", "concept_id": 3000963},
            "Plt": {"ref": "platelets", "concept_id": 3024929},
            "WBC": {"ref": "wbc", "concept_id": 3000905},
        },
        "trends": {
            # Current values
            "hr_current": {"expr": "last(HR)", "type": "float"},
            "sbp_current": {"expr": "last(SBP)", "type": "float"},
            "map_current": {"expr": "last(MAP)", "type": "float"},
            "temp_current": {"expr": "last(Temp)", "type": "float"},
            "resp_current": {"expr": "last(Resp)", "type": "float"},
            "spo2_current": {"expr": "last(SpO2)", "type": "float"},
            "cr_current": {"expr": "last(Cr)", "type": "float"},
            "k_current": {"expr": "last(K)", "type": "float"},
            "na_current": {"expr": "last(Na)", "type": "float"},
            "lactate_current": {"expr": "last(Lactate)", "type": "float"},
            "ph_current": {"expr": "last(pH)", "type": "float"},
            "hgb_current": {"expr": "last(Hgb)", "type": "float"},
            "plt_current": {"expr": "last(Plt)", "type": "float"},
            "wbc_current": {"expr": "last(WBC)", "type": "float"},
            # Deltas
            "hr_delta_6h": {"expr": "delta(HR, 6h)", "type": "float"},
            "sbp_delta_6h": {"expr": "delta(SBP, 6h)", "type": "float"},
            "cr_delta_48h": {"expr": "delta(Cr, 48h)", "type": "float"},
            "lactate_delta_6h": {"expr": "delta(Lactate, 6h)", "type": "float"},
            "hgb_delta_24h": {"expr": "delta(Hgb, 24h)", "type": "float"},
            "plt_delta_24h": {"expr": "delta(Plt, 24h)", "type": "float"},
            # Slopes
            "hr_slope_6h": {"expr": "slope(HR, 6h)", "type": "float"},
            "sbp_slope_6h": {"expr": "slope(SBP, 6h)", "type": "float"},
            "cr_slope_24h": {"expr": "slope(Cr, 24h)", "type": "float"},
            # Min/Max
            "spo2_min_1h": {"expr": "min(SpO2, 1h)", "type": "float"},
            "sbp_min_1h": {"expr": "min(SBP, 1h)", "type": "float"},
        },
        "logic": {
            # Cardiovascular
            "tachycardia": {"when": "hr_current > 100", "severity": "low"},
            "hypotension": {
                "when": "sbp_current < 90 OR map_current < 65",
                "severity": "medium",
            },
            "cv_deterioration": {
                "when": "hr_delta_6h > 20 AND sbp_delta_6h < -20",
                "severity": "high",
            },
            # Respiratory
            "hypoxia": {"when": "spo2_current < 92", "severity": "medium"},
            "tachypnea": {"when": "resp_current > 22", "severity": "low"},
            # Renal
            "aki_stage1": {"when": "cr_delta_48h >= 0.3", "severity": "medium"},
            "hyperkalemia": {"when": "k_current > 6.0", "severity": "high"},
            "hyponatremia": {"when": "na_current < 130", "severity": "medium"},
            # Metabolic
            "lactic_acidosis": {
                "when": "lactate_current > 2.0 AND ph_current < 7.35",
                "severity": "high",
            },
            "acidosis": {"when": "ph_current < 7.35", "severity": "medium"},
            # Hematologic
            "anemia": {"when": "hgb_current < 7.0", "severity": "high"},
            "hemorrhage": {"when": "hgb_delta_24h < -2.0", "severity": "critical"},
            "thrombocytopenia": {"when": "plt_current < 50", "severity": "high"},
            # Composite
            "multisystem_failure": {
                "when": "(cv_deterioration AND aki_stage1) OR (lactic_acidosis AND hypotension)",
                "severity": "critical",
            },
            "rapid_deterioration": {
                "when": "hr_slope_6h > 0 AND sbp_slope_6h < 0 AND lactate_delta_6h > 0.5",
                "severity": "critical",
            },
        },
    },
}


def get_benchmark_scenario(name: str) -> Optional[dict]:
    """
    Get a benchmark scenario by name.

    Args:
        name: Scenario name (simple_threshold, medium_aki, complex_sepsis, very_complex_icu)

    Returns:
        Scenario dictionary or None if not found
    """
    return BENCHMARK_SCENARIOS.get(name)


def list_benchmark_scenarios() -> List[str]:
    """List all available benchmark scenario names."""
    return list(BENCHMARK_SCENARIOS.keys())


def get_scenario_complexity(name: str) -> str:
    """
    Get complexity level of a benchmark scenario.

    Returns: "simple", "medium", "complex", or "very_complex"
    """
    complexity_map = {
        "simple_threshold": "simple",
        "medium_aki": "medium",
        "complex_sepsis": "complex",
        "very_complex_icu": "very_complex",
    }
    return complexity_map.get(name, "unknown")
