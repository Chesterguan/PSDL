"""
PhysioNet Challenge 2019 Data Adapter for PSDL.

This module provides a data adapter for loading and processing
PhysioNet Sepsis Challenge 2019 data files (.psv format).

Usage:
    from psdl.adapters.physionet import PhysioNetBackend

    backend = PhysioNetBackend("path/to/data")
    backend.load_patient("p000001")
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.ir import Signal
from ..operators import DataPoint, TemporalOperators
from ..runtimes.single import DataBackend

# PhysioNet column mappings to standardized signal names
PHYSIONET_SIGNALS = {
    # Vitals
    "HR": "HeartRate",
    "O2Sat": "SpO2",
    "Temp": "Temperature",
    "SBP": "SystolicBP",
    "MAP": "MeanArterialPressure",
    "DBP": "DiastolicBP",
    "Resp": "RespiratoryRate",
    "EtCO2": "EndTidalCO2",
    # Blood gas
    "BaseExcess": "BaseExcess",
    "HCO3": "Bicarbonate",
    "FiO2": "FiO2",
    "pH": "pH",
    "PaCO2": "PaCO2",
    "SaO2": "SaO2",
    # Labs
    "AST": "AST",
    "BUN": "BUN",
    "Alkalinephos": "AlkalinePhosphatase",
    "Calcium": "Calcium",
    "Chloride": "Chloride",
    "Creatinine": "Creatinine",
    "Bilirubin_direct": "DirectBilirubin",
    "Glucose": "Glucose",
    "Lactate": "Lactate",
    "Magnesium": "Magnesium",
    "Phosphate": "Phosphate",
    "Potassium": "Potassium",
    "Bilirubin_total": "TotalBilirubin",
    "TroponinI": "TroponinI",
    "Hct": "Hematocrit",
    "Hgb": "Hemoglobin",
    "PTT": "PTT",
    "WBC": "WBC",
    "Fibrinogen": "Fibrinogen",
    "Platelets": "Platelets",
    # Demographics (static)
    "Age": "Age",
    "Gender": "Gender",
    "Unit1": "Unit1",
    "Unit2": "Unit2",
    "HospAdmTime": "HospAdmTime",
    # Time and outcome
    "ICULOS": "ICULOS",
    "SepsisLabel": "SepsisLabel",
}

# Reverse mapping: standardized name -> PhysioNet column
REVERSE_SIGNALS = {v: k for k, v in PHYSIONET_SIGNALS.items()}


class PhysioNetBackend(DataBackend):
    """
    Data backend for PhysioNet Challenge 2019 sepsis data.

    Loads .psv files and provides signal data for PSDL evaluation.
    """

    def __init__(
        self,
        data_path: Union[str, Path],
        base_datetime: Optional[datetime] = None,
    ):
        """
        Initialize PhysioNet backend.

        Args:
            data_path: Path to directory containing .psv files
            base_datetime: Base datetime for timestamps (default: 2024-01-01)
        """
        self.data_path = Path(data_path)
        self.base_datetime = base_datetime or datetime(2024, 1, 1, 0, 0, 0)
        self._patient_data: Dict[str, Dict[str, List[DataPoint]]] = {}
        self._patient_metadata: Dict[str, Dict] = {}
        self._current_patient: Optional[str] = None

    def load_patient(self, patient_id: str) -> bool:
        """
        Load a patient's data from a .psv file.

        Args:
            patient_id: Patient identifier (e.g., "p000001" or just "000001")

        Returns:
            True if loaded successfully, False otherwise
        """
        # Normalize patient ID format
        if not patient_id.startswith("p"):
            patient_id = f"p{patient_id.zfill(6)}"

        psv_file = self.data_path / f"{patient_id}.psv"
        if not psv_file.exists():
            return False

        self._patient_data[patient_id] = {}
        self._patient_metadata[patient_id] = {}

        with open(psv_file, "r") as f:
            lines = f.readlines()

        if not lines:
            return False

        # Parse header
        header = lines[0].strip().split("|")
        col_indices = {col: i for i, col in enumerate(header)}

        # Parse data rows
        sepsis_onset_hour: Optional[int] = None
        for line in lines[1:]:
            parts = line.strip().split("|")
            if len(parts) != len(header):
                continue

            # Get ICULOS (hour index)
            iculos_idx = col_indices.get("ICULOS")
            if iculos_idx is None:
                continue
            try:
                hour = int(float(parts[iculos_idx]))
            except (ValueError, IndexError):
                continue

            timestamp = self.base_datetime + timedelta(hours=hour)

            # Check for sepsis label
            sepsis_idx = col_indices.get("SepsisLabel")
            if sepsis_idx is not None:
                try:
                    sepsis_label = int(float(parts[sepsis_idx]))
                    if sepsis_label == 1 and sepsis_onset_hour is None:
                        sepsis_onset_hour = hour
                except (ValueError, IndexError):
                    pass

            # Parse each signal
            for col_name, signal_name in PHYSIONET_SIGNALS.items():
                idx = col_indices.get(col_name)
                if idx is None:
                    continue

                value_str = parts[idx].strip()
                if value_str == "NaN" or value_str == "":
                    continue

                try:
                    value = float(value_str)
                except ValueError:
                    continue

                if signal_name not in self._patient_data[patient_id]:
                    self._patient_data[patient_id][signal_name] = []

                self._patient_data[patient_id][signal_name].append(
                    DataPoint(timestamp=timestamp, value=value)
                )

        # Store metadata
        self._patient_metadata[patient_id] = {
            "sepsis_onset_hour": sepsis_onset_hour,
            "has_sepsis": sepsis_onset_hour is not None,
            "total_hours": hour if "hour" in dir() else 0,
        }

        self._current_patient = patient_id
        return True

    def get_signal_data(
        self,
        signal_name: str,
        patient_id: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[DataPoint]:
        """
        Get signal data for a patient.

        Args:
            signal_name: Name of signal (standardized or PhysioNet column name)
            patient_id: Patient ID (uses current if not specified)
            reference_time: Filter data up to this time

        Returns:
            List of DataPoint objects
        """
        pid = patient_id or self._current_patient
        if pid is None or pid not in self._patient_data:
            return []

        # Map PhysioNet column name to standardized name if needed
        if signal_name in PHYSIONET_SIGNALS:
            signal_name = PHYSIONET_SIGNALS[signal_name]

        data = self._patient_data.get(pid, {}).get(signal_name, [])

        if reference_time is not None:
            data = [dp for dp in data if dp.timestamp <= reference_time]

        return data

    def get_patient_metadata(self, patient_id: Optional[str] = None) -> Dict:
        """Get metadata for a patient."""
        pid = patient_id or self._current_patient
        if pid is None:
            return {}
        return self._patient_metadata.get(pid, {})

    def list_patients(self) -> List[str]:
        """List all available patient IDs in the data directory."""
        return sorted([f.stem for f in self.data_path.glob("p*.psv")])

    def list_signals(self, patient_id: Optional[str] = None) -> List[str]:
        """List available signals for a patient."""
        pid = patient_id or self._current_patient
        if pid is None or pid not in self._patient_data:
            return []
        return sorted(self._patient_data[pid].keys())

    def get_sepsis_onset_time(self, patient_id: Optional[str] = None) -> Optional[datetime]:
        """Get sepsis onset time for a patient (if sepsis case)."""
        meta = self.get_patient_metadata(patient_id)
        onset_hour = meta.get("sepsis_onset_hour")
        if onset_hour is not None:
            return self.base_datetime + timedelta(hours=onset_hour)
        return None

    # DataBackend abstract methods implementation
    def fetch_signal_data(
        self,
        patient_id: Any,
        signal: Signal,
        window_seconds: int,
        reference_time: datetime,
    ) -> List[DataPoint]:
        """
        Fetch time-series data for a signal (DataBackend interface).

        Args:
            patient_id: Patient identifier
            signal: Signal definition
            window_seconds: How far back to fetch
            reference_time: End of the time window

        Returns:
            List of DataPoints sorted by timestamp (ascending)
        """
        # Ensure patient is loaded
        pid = str(patient_id)
        if pid not in self._patient_data:
            self.load_patient(pid)

        # Get signal name from source or name
        signal_name = signal.source if hasattr(signal, "source") and signal.source else signal.name

        # Map to PhysioNet signal name if needed
        if signal_name in PHYSIONET_SIGNALS:
            signal_name = PHYSIONET_SIGNALS[signal_name]

        # Get all data for this signal
        data = self._patient_data.get(pid, {}).get(signal_name, [])

        # Filter by window
        return TemporalOperators.filter_by_window(data, window_seconds, reference_time)

    def get_patient_ids(
        self,
        population_include: Optional[List[str]] = None,
        population_exclude: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Get patient IDs (DataBackend interface).

        Args:
            population_include: Inclusion criteria (not implemented)
            population_exclude: Exclusion criteria (not implemented)

        Returns:
            List of patient IDs from loaded data
        """
        # Return already loaded patients, or list all from directory
        if self._patient_data:
            return list(self._patient_data.keys())
        return self.list_patients()


def load_physionet_dataset(
    data_path: Union[str, Path],
    max_patients: Optional[int] = None,
) -> PhysioNetBackend:
    """
    Load PhysioNet dataset and return a configured backend.

    Args:
        data_path: Path to directory containing .psv files
        max_patients: Maximum number of patients to pre-load

    Returns:
        Configured PhysioNetBackend instance
    """
    backend = PhysioNetBackend(data_path)
    patient_ids = backend.list_patients()

    if max_patients is not None:
        patient_ids = patient_ids[:max_patients]

    for pid in patient_ids:
        backend.load_patient(pid)

    return backend
