"""
Synthetic Data Generator for PSDL Benchmarks.

Generates realistic clinical data for benchmarking PSDL scenarios.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from psdl.operators import DataPoint


@dataclass
class SyntheticDataConfig:
    """Configuration for synthetic data generation."""

    # Patient settings
    num_patients: int = 100
    patient_id_prefix: str = "P"

    # Time settings
    start_time: datetime = field(default_factory=lambda: datetime(2024, 1, 1))
    duration_hours: int = 72  # 3 days of data per patient

    # Measurement frequency (per hour)
    vital_frequency: float = 4.0  # Every 15 minutes
    lab_frequency: float = 0.17  # Every 6 hours

    # Random seed for reproducibility
    seed: Optional[int] = None

    # Signal configurations (name -> (mean, std, unit))
    signals: Dict[str, tuple] = field(
        default_factory=lambda: {
            # Vitals
            "HR": (80, 15, "bpm"),
            "SBP": (120, 20, "mmHg"),
            "DBP": (80, 10, "mmHg"),
            "SpO2": (97, 3, "%"),
            "Temp": (37.0, 0.5, "C"),
            "Resp": (16, 4, "breaths/min"),
            # Labs
            "Cr": (1.0, 0.3, "mg/dL"),
            "Lactate": (1.5, 0.8, "mmol/L"),
            "K": (4.0, 0.5, "mEq/L"),
            "WBC": (8.0, 3.0, "10^9/L"),
            "Hgb": (13.0, 2.0, "g/dL"),
            "pH": (7.40, 0.05, ""),
        }
    )

    # Signals that are "vitals" (more frequent)
    vital_signals: List[str] = field(
        default_factory=lambda: ["HR", "SBP", "DBP", "SpO2", "Temp", "Resp"]
    )


def generate_synthetic_data(
    num_patients: int = 100,
    config: Optional[SyntheticDataConfig] = None,
) -> Dict[str, Dict[str, List[DataPoint]]]:
    """
    Generate synthetic patient data for benchmarking.

    Args:
        num_patients: Number of patients to generate
        config: Optional configuration (uses defaults if not provided)

    Returns:
        Dictionary mapping patient_id -> signal_name -> list of DataPoints
    """
    if config is None:
        config = SyntheticDataConfig(num_patients=num_patients)
    else:
        config.num_patients = num_patients

    if config.seed is not None:
        random.seed(config.seed)

    data: Dict[str, Dict[str, List[DataPoint]]] = {}

    for i in range(config.num_patients):
        patient_id = f"{config.patient_id_prefix}{i:05d}"
        data[patient_id] = _generate_patient_data(patient_id, config)

    return data


def _generate_patient_data(
    patient_id: str,
    config: SyntheticDataConfig,
) -> Dict[str, List[DataPoint]]:
    """Generate data for a single patient."""
    patient_data: Dict[str, List[DataPoint]] = {}

    end_time = config.start_time + timedelta(hours=config.duration_hours)

    for signal_name, (mean, std, unit) in config.signals.items():
        is_vital = signal_name in config.vital_signals
        frequency = config.vital_frequency if is_vital else config.lab_frequency

        # Generate timestamps
        timestamps = _generate_timestamps(
            config.start_time,
            end_time,
            frequency,
        )

        # Generate values with some temporal correlation
        values = _generate_correlated_values(
            len(timestamps),
            mean,
            std,
            correlation=0.8 if is_vital else 0.5,  # Vitals more correlated
        )

        # Create DataPoints (DataPoint only has timestamp and value)
        patient_data[signal_name] = [
            DataPoint(
                timestamp=ts,
                value=val,
            )
            for ts, val in zip(timestamps, values)
        ]

    return patient_data


def _generate_timestamps(
    start: datetime,
    end: datetime,
    frequency: float,  # per hour
) -> List[datetime]:
    """Generate timestamps with some random variation."""
    timestamps = []
    current = start

    # Average interval in minutes
    avg_interval = 60.0 / frequency

    while current < end:
        # Add some randomness to the interval
        jitter = random.gauss(0, avg_interval * 0.1)
        interval = max(1, avg_interval + jitter)

        timestamps.append(current)
        current = current + timedelta(minutes=interval)

    return timestamps


def _generate_correlated_values(
    n: int,
    mean: float,
    std: float,
    correlation: float = 0.8,
) -> List[float]:
    """Generate temporally correlated values using AR(1) process."""
    values = []
    prev = mean

    for _ in range(n):
        # AR(1) process: x_t = correlation * x_{t-1} + noise
        noise = random.gauss(0, std * (1 - correlation**2) ** 0.5)
        value = mean + correlation * (prev - mean) + noise
        values.append(value)
        prev = value

    return values


def generate_aki_scenario_data(
    num_patients: int = 100,
    aki_rate: float = 0.1,  # 10% develop AKI
    seed: Optional[int] = None,
) -> Dict[str, Dict[str, List[DataPoint]]]:
    """
    Generate data specifically for AKI detection benchmarks.

    A portion of patients will have rising creatinine patterns.

    Args:
        num_patients: Number of patients
        aki_rate: Fraction of patients who develop AKI
        seed: Random seed for reproducibility

    Returns:
        Patient data with AKI patterns
    """
    if seed is not None:
        random.seed(seed)

    config = SyntheticDataConfig(
        num_patients=num_patients,
        duration_hours=72,
        seed=seed,
    )

    data = generate_synthetic_data(num_patients, config)

    # Add AKI patterns to some patients
    num_aki = int(num_patients * aki_rate)
    aki_patients = random.sample(list(data.keys()), num_aki)

    for patient_id in aki_patients:
        # Replace creatinine with rising pattern
        cr_data = data[patient_id]["Cr"]
        base_cr = random.uniform(0.8, 1.2)
        rise_rate = random.uniform(0.5, 1.5)

        for i, dp in enumerate(cr_data):
            # Linear rise over time
            progress = i / len(cr_data)
            cr_rise = base_cr + progress * rise_rate
            cr_data[i] = DataPoint(
                timestamp=dp.timestamp,
                value=cr_rise + random.gauss(0, 0.1),
            )

    return data


def generate_sepsis_scenario_data(
    num_patients: int = 100,
    sepsis_rate: float = 0.15,  # 15% develop sepsis
    seed: Optional[int] = None,
) -> Dict[str, Dict[str, List[DataPoint]]]:
    """
    Generate data specifically for sepsis detection benchmarks.

    A portion of patients will have SIRS patterns with elevated lactate.

    Args:
        num_patients: Number of patients
        sepsis_rate: Fraction of patients who develop sepsis
        seed: Random seed for reproducibility

    Returns:
        Patient data with sepsis patterns
    """
    if seed is not None:
        random.seed(seed)

    config = SyntheticDataConfig(
        num_patients=num_patients,
        duration_hours=48,
        seed=seed,
    )

    data = generate_synthetic_data(num_patients, config)

    # Add sepsis patterns to some patients
    num_sepsis = int(num_patients * sepsis_rate)
    sepsis_patients = random.sample(list(data.keys()), num_sepsis)

    for patient_id in sepsis_patients:
        patient_data = data[patient_id]

        # Elevate heart rate
        for dp in patient_data["HR"]:
            dp.value = max(dp.value, 100 + random.gauss(0, 10))

        # Elevate respiratory rate
        for dp in patient_data["Resp"]:
            dp.value = max(dp.value, 24 + random.gauss(0, 3))

        # Elevate temperature (or hypothermia in 20% of cases)
        if random.random() < 0.2:
            for dp in patient_data["Temp"]:
                dp.value = min(dp.value, 35.5 + random.gauss(0, 0.3))
        else:
            for dp in patient_data["Temp"]:
                dp.value = max(dp.value, 38.5 + random.gauss(0, 0.5))

        # Elevate lactate
        for dp in patient_data["Lactate"]:
            dp.value = max(dp.value, 2.5 + random.gauss(0, 0.8))

        # Elevate WBC
        for dp in patient_data["WBC"]:
            if random.random() < 0.7:  # 70% leukocytosis
                dp.value = max(dp.value, 13 + random.gauss(0, 3))
            else:  # 30% leukopenia
                dp.value = min(dp.value, 3.5 + random.gauss(0, 0.5))

    return data
