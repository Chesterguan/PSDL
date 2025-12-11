"""
PSDL Mapping Provider - Translates logical signal names to local terminology.

The mapping layer is the key to PSDL portability:
- PSDL scenarios use logical signal names (e.g., "creatinine", "potassium")
- Each institution creates a mapping file that translates to their local codes
- The adapter (OMOP, FHIR) handles data format, not terminology

Workflow:
    1. Researcher writes PSDL scenario with logical signal names
    2. Hospital creates mapping file for their data
    3. PSDL runtime combines scenario + mapping + adapter to execute

Example:
    # Load mapping for your institution
    mapping = MappingProvider.from_file("mappings/hospital_a.yaml")

    # Create adapter with mapping
    backend = OMOPBackend(config, mapping=mapping)

    # Run scenario (portable across institutions)
    evaluator = PSDLEvaluator(scenario, backend)
    results = evaluator.evaluate_cohort()
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class SignalMapping:
    """Mapping for a single signal from logical name to local terminology."""

    # OMOP-style mapping
    concept_id: Optional[int] = None

    # Source value mapping (for unmapped OMOP databases)
    source_value: Optional[str] = None

    # FHIR-style mapping
    loinc_code: Optional[str] = None
    fhir_code_system: Optional[str] = None

    # Unit conversion (if needed)
    unit: Optional[str] = None
    unit_conversion_factor: Optional[float] = None

    # Additional metadata
    description: Optional[str] = None


@dataclass
class MappingProvider:
    """
    Provides terminology mappings from logical signal names to local codes.

    This is the bridge between portable PSDL scenarios and institution-specific
    data. Each hospital creates their own mapping file.

    Supports:
    - OMOP concept IDs (for standard mapped data)
    - OMOP source values (for unmapped data like MIMIC-IV)
    - FHIR LOINC codes
    - Unit conversions
    """

    # Institution metadata
    institution: str = "Unknown"
    description: str = ""
    data_source: str = ""  # e.g., "OMOP CDM 5.4", "FHIR R4"

    # Signal mappings: logical_name -> SignalMapping
    signals: Dict[str, SignalMapping] = field(default_factory=dict)

    # Default settings for this institution
    use_source_values: bool = False  # For OMOP: use source_value instead of concept_id

    def get_concept_id(self, signal_name: str) -> Optional[int]:
        """Get OMOP concept_id for a signal."""
        if signal_name in self.signals:
            return self.signals[signal_name].concept_id
        return None

    def get_source_value(self, signal_name: str) -> Optional[str]:
        """Get source_value for a signal (for unmapped OMOP)."""
        if signal_name in self.signals:
            return self.signals[signal_name].source_value
        return None

    def get_loinc_code(self, signal_name: str) -> Optional[str]:
        """Get LOINC code for a signal (for FHIR)."""
        if signal_name in self.signals:
            return self.signals[signal_name].loinc_code
        return None

    def get_unit(self, signal_name: str) -> Optional[str]:
        """Get expected unit for a signal."""
        if signal_name in self.signals:
            return self.signals[signal_name].unit
        return None

    def has_signal(self, signal_name: str) -> bool:
        """Check if a signal is mapped."""
        return signal_name in self.signals

    def list_signals(self) -> List[str]:
        """List all mapped signal names."""
        return list(self.signals.keys())

    @classmethod
    def from_file(cls, filepath: str) -> "MappingProvider":
        """
        Load mapping from a YAML file.

        Args:
            filepath: Path to YAML mapping file

        Returns:
            MappingProvider instance
        """
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MappingProvider":
        """
        Create mapping from a dictionary.

        Args:
            data: Mapping configuration dictionary

        Returns:
            MappingProvider instance
        """
        signals = {}
        for name, spec in data.get("signals", {}).items():
            if isinstance(spec, dict):
                signals[name] = SignalMapping(
                    concept_id=spec.get("concept_id"),
                    source_value=spec.get("source_value"),
                    loinc_code=spec.get("loinc_code"),
                    fhir_code_system=spec.get("fhir_code_system"),
                    unit=spec.get("unit"),
                    unit_conversion_factor=spec.get("unit_conversion_factor"),
                    description=spec.get("description"),
                )
            elif isinstance(spec, int):
                # Shorthand: just concept_id
                signals[name] = SignalMapping(concept_id=spec)
            elif isinstance(spec, str):
                # Shorthand: just source_value
                signals[name] = SignalMapping(source_value=spec)

        return cls(
            institution=data.get("institution", "Unknown"),
            description=data.get("description", ""),
            data_source=data.get("data_source", ""),
            signals=signals,
            use_source_values=data.get("use_source_values", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Export mapping to dictionary."""
        signals_dict = {}
        for name, mapping in self.signals.items():
            sig = {}
            if mapping.concept_id is not None:
                sig["concept_id"] = mapping.concept_id
            if mapping.source_value is not None:
                sig["source_value"] = mapping.source_value
            if mapping.loinc_code is not None:
                sig["loinc_code"] = mapping.loinc_code
            if mapping.unit is not None:
                sig["unit"] = mapping.unit
            if mapping.description is not None:
                sig["description"] = mapping.description
            signals_dict[name] = sig

        return {
            "institution": self.institution,
            "description": self.description,
            "data_source": self.data_source,
            "use_source_values": self.use_source_values,
            "signals": signals_dict,
        }

    def save(self, filepath: str):
        """Save mapping to a YAML file."""
        with open(filepath, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)


def load_mapping(filepath: str) -> MappingProvider:
    """
    Convenience function to load a mapping file.

    Args:
        filepath: Path to YAML mapping file

    Returns:
        MappingProvider instance

    Example:
        mapping = load_mapping("mappings/mimic_iv.yaml")
        backend = OMOPBackend(config, mapping=mapping)
    """
    return MappingProvider.from_file(filepath)


# Pre-built mappings for common public datasets
def get_mimic_iv_mapping() -> MappingProvider:
    """
    Get pre-configured mapping for MIMIC-IV OMOP database.

    MIMIC-IV in OMOP format has unmapped concepts (concept_id=0),
    so we use source_value lookups instead.
    """
    return MappingProvider(
        institution="MIMIC-IV",
        description="Mapping for MIMIC-IV data in OMOP CDM format",
        data_source="OMOP CDM 5.4 (unmapped)",
        use_source_values=True,
        signals={
            "creatinine": SignalMapping(
                source_value="Creatinine",
                loinc_code="2160-0",
                unit="mg/dL",
                description="Serum creatinine",
            ),
            "potassium": SignalMapping(
                source_value="Potassium",
                loinc_code="2823-3",
                unit="mEq/L",
                description="Serum potassium",
            ),
            "lactate": SignalMapping(
                source_value="Lactate",
                loinc_code="2524-7",
                unit="mmol/L",
                description="Blood lactate",
            ),
            "hemoglobin": SignalMapping(
                source_value="Hemoglobin",
                loinc_code="718-7",
                unit="g/dL",
                description="Blood hemoglobin",
            ),
            "bun": SignalMapping(
                source_value="Urea Nitrogen",
                loinc_code="3094-0",
                unit="mg/dL",
                description="Blood urea nitrogen",
            ),
            "heart_rate": SignalMapping(
                source_value="Heart Rate",
                loinc_code="8867-4",
                unit="bpm",
                description="Heart rate",
            ),
            "sbp": SignalMapping(
                source_value="Systolic Blood Pressure",
                loinc_code="8480-6",
                unit="mmHg",
                description="Systolic blood pressure",
            ),
            "dbp": SignalMapping(
                source_value="Diastolic Blood Pressure",
                loinc_code="8462-4",
                unit="mmHg",
                description="Diastolic blood pressure",
            ),
            "temperature": SignalMapping(
                source_value="Temperature",
                loinc_code="8310-5",
                unit="C",
                description="Body temperature",
            ),
            "respiratory_rate": SignalMapping(
                source_value="Respiratory Rate",
                loinc_code="9279-1",
                unit="/min",
                description="Respiratory rate",
            ),
            "spo2": SignalMapping(
                source_value="SpO2",
                loinc_code="59408-5",
                unit="%",
                description="Oxygen saturation",
            ),
            "wbc": SignalMapping(
                source_value="White Blood Cells",
                loinc_code="6690-2",
                unit="K/uL",
                description="White blood cell count",
            ),
            "platelets": SignalMapping(
                source_value="Platelet Count",
                loinc_code="777-3",
                unit="K/uL",
                description="Platelet count",
            ),
        },
    )


def get_synthea_mapping() -> MappingProvider:
    """
    Get pre-configured mapping for Synthea synthetic data.

    Synthea uses standard OMOP concept IDs.
    """
    return MappingProvider(
        institution="Synthea",
        description="Mapping for Synthea synthetic patient data",
        data_source="OMOP CDM 5.4 (standard concepts)",
        use_source_values=False,
        signals={
            "creatinine": SignalMapping(
                concept_id=3016723,
                loinc_code="2160-0",
                unit="mg/dL",
                description="Serum creatinine",
            ),
            "potassium": SignalMapping(
                concept_id=3023103,
                loinc_code="2823-3",
                unit="mEq/L",
                description="Serum potassium",
            ),
            "lactate": SignalMapping(
                concept_id=3047181,
                loinc_code="2524-7",
                unit="mmol/L",
                description="Blood lactate",
            ),
            "hemoglobin": SignalMapping(
                concept_id=3000963,
                loinc_code="718-7",
                unit="g/dL",
                description="Blood hemoglobin",
            ),
            "bun": SignalMapping(
                concept_id=3013682,
                loinc_code="3094-0",
                unit="mg/dL",
                description="Blood urea nitrogen",
            ),
            "heart_rate": SignalMapping(
                concept_id=3027018,
                loinc_code="8867-4",
                unit="bpm",
                description="Heart rate",
            ),
        },
    )
