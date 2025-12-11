"""
PSDL FHIR R4 Backend

Connects PSDL to FHIR R4 servers for real-time clinical data access.

Reference: https://hl7.org/fhir/R4/

Usage:
    from psdl.backends import FHIRBackend, FHIRConfig

    config = FHIRConfig(
        base_url="https://fhir.hospital.org/r4",
        auth_token="Bearer xxx"
    )
    backend = FHIRBackend(config)

    evaluator = PSDLEvaluator(scenario, backend)
    result = evaluator.evaluate_patient(patient_id="patient-uuid")
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore
    REQUESTS_AVAILABLE = False

from ..core.ir import Signal
from ..operators import DataPoint
from ..runtimes.single import DataBackend

if TYPE_CHECKING:
    from ..mapping import MappingProvider


class FHIRResourceType(Enum):
    """FHIR resource types for clinical data."""

    OBSERVATION = "Observation"
    CONDITION = "Condition"
    MEDICATION_REQUEST = "MedicationRequest"
    MEDICATION_ADMINISTRATION = "MedicationAdministration"
    PROCEDURE = "Procedure"
    DIAGNOSTIC_REPORT = "DiagnosticReport"


# Mapping from PSDL domain to FHIR resource type
DOMAIN_RESOURCE_MAP = {
    "measurement": FHIRResourceType.OBSERVATION,
    "observation": FHIRResourceType.OBSERVATION,
    "condition": FHIRResourceType.CONDITION,
    "drug": FHIRResourceType.MEDICATION_ADMINISTRATION,
    "procedure": FHIRResourceType.PROCEDURE,
}

# Common LOINC codes for clinical measurements
LOINC_CODES = {
    "creatinine": "2160-0",
    "lactate": "2524-7",
    "glucose": "2345-7",
    "heart_rate": "8867-4",
    "respiratory_rate": "9279-1",
    "oxygen_saturation": "2708-6",
    "systolic_blood_pressure": "8480-6",
    "diastolic_blood_pressure": "8462-4",
    "body_temperature": "8310-5",
    "hemoglobin": "718-7",
    "potassium": "2823-3",
    "sodium": "2951-2",
    "bun": "3094-0",
    "wbc": "6690-2",
    "platelets": "777-3",
    "gcs": "9269-2",
}


@dataclass
class FHIRConfig:
    """
    Configuration for FHIR R4 backend.

    Args:
        base_url: FHIR server base URL (e.g., "https://fhir.hospital.org/r4")
        auth_token: Authorization token (e.g., "Bearer xxx" or API key)
        auth_type: Type of authentication ("bearer", "basic", "none")
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
        headers: Additional HTTP headers
        loinc_mappings: Override LOINC code mappings for signals
    """

    base_url: str
    auth_token: Optional[str] = None
    auth_type: str = "bearer"
    timeout: int = 30
    verify_ssl: bool = True
    headers: Dict[str, str] = field(default_factory=dict)
    loinc_mappings: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Remove trailing slash from base_url
        self.base_url = self.base_url.rstrip("/")


class FHIRBackend(DataBackend):
    """
    FHIR R4 data backend for PSDL.

    Fetches clinical data from FHIR R4 servers and converts
    to PSDL DataPoint format for evaluation.

    Supports:
    - Observations (labs, vitals)
    - Conditions
    - MedicationAdministration
    - Procedures

    Example:
        config = FHIRConfig(
            base_url="https://fhir.example.org/r4",
            auth_token="Bearer my-token"
        )
        backend = FHIRBackend(config)

        evaluator = PSDLEvaluator(scenario, backend)
        result = evaluator.evaluate_patient("patient-uuid")

    Example with mapping:
        from psdl.mapping import load_mapping

        mapping = load_mapping("mappings/synthea.yaml")
        backend = FHIRBackend(config, mapping=mapping)
    """

    def __init__(self, config: FHIRConfig, mapping: Optional["MappingProvider"] = None):
        """
        Initialize FHIR backend with configuration.

        Args:
            config: FHIRConfig with connection details
            mapping: Optional MappingProvider for signal-to-LOINC translation
        """
        self.config = config
        self.mapping = mapping
        self._session = None

    def _get_session(self):
        """Lazy initialization of HTTP session."""
        if self._session is None:
            if not REQUESTS_AVAILABLE:
                raise ImportError(
                    "requests library is required for FHIR backend. "
                    "Install with: pip install requests"
                )

            self._session = requests.Session()

            # Set default headers
            self._session.headers.update(
                {
                    "Accept": "application/fhir+json",
                    "Content-Type": "application/fhir+json",
                }
            )

            # Add authentication
            if self.config.auth_token:
                if self.config.auth_type == "bearer":
                    self._session.headers["Authorization"] = (
                        f"Bearer {self.config.auth_token}"
                        if not self.config.auth_token.startswith("Bearer")
                        else self.config.auth_token
                    )
                elif self.config.auth_type == "basic":
                    self._session.headers["Authorization"] = f"Basic {self.config.auth_token}"

            # Add custom headers
            self._session.headers.update(self.config.headers)

            # SSL verification
            self._session.verify = self.config.verify_ssl

        return self._session

    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        """Make a GET request to the FHIR server."""
        session = self._get_session()
        url = f"{self.config.base_url}/{endpoint}"

        try:
            response = session.get(url, params=params, timeout=self.config.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise RuntimeError(f"FHIR request failed: {e}")

    def _get_loinc_code(self, signal: Signal) -> Optional[str]:
        """
        Get LOINC code for a signal.

        Priority:
        1. MappingProvider (if provided)
        2. Config-level loinc_mappings override
        3. Signal source name lookup in LOINC_CODES
        4. Signal source if it looks like a LOINC code
        """
        # Check MappingProvider first (new recommended approach)
        if self.mapping is not None:
            loinc_code = self.mapping.get_loinc_code(signal.source or signal.name)
            if loinc_code:
                return loinc_code

        # Check config overrides
        if signal.name in self.config.loinc_mappings:
            return self.config.loinc_mappings[signal.name]

        # Check common mappings by source name
        source_lower = signal.source.lower().replace(" ", "_").replace("-", "_")
        if source_lower in LOINC_CODES:
            return LOINC_CODES[source_lower]

        # Check if source is already a LOINC code (format: digits-digit)
        if signal.source and "-" in signal.source:
            parts = signal.source.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return signal.source

        return None

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        """Parse FHIR datetime string to Python datetime."""
        if not value:
            return None

        # FHIR datetime formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value.replace("+00:00", "Z"), fmt)
            except ValueError:
                continue

        return None

    def _extract_observation_value(self, observation: Dict) -> Optional[float]:
        """Extract numeric value from FHIR Observation resource."""
        # valueQuantity - most common for labs/vitals
        if "valueQuantity" in observation:
            return observation["valueQuantity"].get("value")

        # valueInteger
        if "valueInteger" in observation:
            return float(observation["valueInteger"])

        # valueString that might be numeric
        if "valueString" in observation:
            try:
                return float(observation["valueString"])
            except ValueError:
                return None

        # component values (e.g., blood pressure)
        if "component" in observation:
            # Return first component value
            for comp in observation["component"]:
                if "valueQuantity" in comp:
                    return comp["valueQuantity"].get("value")

        return None

    def _extract_observation_datetime(self, observation: Dict) -> Optional[datetime]:
        """Extract datetime from FHIR Observation resource."""
        # effectiveDateTime - most common
        if "effectiveDateTime" in observation:
            return self._parse_datetime(observation["effectiveDateTime"])

        # effectivePeriod - use start
        if "effectivePeriod" in observation:
            period = observation["effectivePeriod"]
            if "start" in period:
                return self._parse_datetime(period["start"])

        # effectiveInstant
        if "effectiveInstant" in observation:
            return self._parse_datetime(observation["effectiveInstant"])

        # Fall back to issued date
        if "issued" in observation:
            return self._parse_datetime(observation["issued"])

        return None

    def fetch_signal_data(
        self,
        patient_id: Any,
        signal: Signal,
        window_seconds: int,
        reference_time: datetime,
    ) -> List[DataPoint]:
        """
        Fetch time-series data for a signal from FHIR server.

        Args:
            patient_id: FHIR Patient ID (UUID or reference)
            signal: Signal definition
            window_seconds: How far back to fetch
            reference_time: End of the time window

        Returns:
            List of DataPoints sorted by timestamp (ascending)
        """
        domain = signal.domain.value if signal.domain else "measurement"
        resource_type = DOMAIN_RESOURCE_MAP.get(domain, FHIRResourceType.OBSERVATION).value

        window_start = reference_time - timedelta(seconds=window_seconds)

        # Build search parameters
        params = {
            "patient": patient_id,
            "_sort": "date",
            "date": [
                f"ge{window_start.strftime('%Y-%m-%dT%H:%M:%S')}",
                f"le{reference_time.strftime('%Y-%m-%dT%H:%M:%S')}",
            ],
        }

        # Add code filter for Observations
        if resource_type == "Observation":
            loinc_code = self._get_loinc_code(signal)
            if loinc_code:
                params["code"] = f"http://loinc.org|{loinc_code}"

        # Make request
        try:
            bundle = self._make_request(resource_type, params)
        except Exception:
            return []

        # Extract data points
        data_points = []

        if bundle.get("resourceType") == "Bundle" and "entry" in bundle:
            for entry in bundle["entry"]:
                resource = entry.get("resource", {})

                if resource.get("resourceType") == "Observation":
                    value = self._extract_observation_value(resource)
                    timestamp = self._extract_observation_datetime(resource)

                    if value is not None and timestamp is not None:
                        data_points.append(DataPoint(timestamp=timestamp, value=value))

                elif resource.get("resourceType") == "Condition":
                    # For conditions, return 1.0 for presence
                    onset = resource.get("onsetDateTime") or resource.get("recordedDate")
                    if onset:
                        timestamp = self._parse_datetime(onset)
                        if timestamp:
                            data_points.append(DataPoint(timestamp=timestamp, value=1.0))

        # Sort by timestamp
        data_points.sort(key=lambda dp: dp.timestamp)

        return data_points

    def get_patient_ids(
        self,
        population_include: Optional[List[str]] = None,
        population_exclude: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Get patient IDs from FHIR server.

        Note: Population filter parsing is not yet implemented.
        Returns all patient IDs from the server (paginated).

        Args:
            population_include: Inclusion criteria (not yet implemented)
            population_exclude: Exclusion criteria (not yet implemented)

        Returns:
            List of patient IDs
        """
        patient_ids = []
        next_url = "Patient?_elements=id&_count=100"

        while next_url:
            try:
                if next_url.startswith("http"):
                    # Full URL from pagination
                    session = self._get_session()
                    response = session.get(next_url, timeout=self.config.timeout)
                    response.raise_for_status()
                    bundle = response.json()
                else:
                    bundle = self._make_request(next_url)

                if bundle.get("resourceType") == "Bundle" and "entry" in bundle:
                    for entry in bundle["entry"]:
                        resource = entry.get("resource", {})
                        if "id" in resource:
                            patient_ids.append(resource["id"])

                # Check for next page
                next_url = None
                for link in bundle.get("link", []):
                    if link.get("relation") == "next":
                        next_url = link.get("url")
                        break

            except Exception:
                break

        return patient_ids

    def get_patient(self, patient_id: str) -> Optional[Dict]:
        """
        Get patient resource by ID.

        Args:
            patient_id: FHIR Patient ID

        Returns:
            Patient resource as dict, or None if not found
        """
        try:
            return self._make_request(f"Patient/{patient_id}")
        except Exception:
            return None

    def search_patients_with_observation(
        self,
        loinc_code: str,
        min_count: int = 1,
    ) -> List[str]:
        """
        Find patients who have observations with a specific LOINC code.

        Args:
            loinc_code: LOINC code to search for
            min_count: Minimum number of observations required

        Returns:
            List of patient IDs
        """
        patient_ids = set()

        try:
            params = {
                "code": f"http://loinc.org|{loinc_code}",
                "_elements": "subject",
                "_count": 1000,
            }
            bundle = self._make_request("Observation", params)

            if bundle.get("resourceType") == "Bundle" and "entry" in bundle:
                for entry in bundle["entry"]:
                    resource = entry.get("resource", {})
                    subject = resource.get("subject", {})
                    ref = subject.get("reference", "")
                    if ref.startswith("Patient/"):
                        patient_ids.add(ref.replace("Patient/", ""))

        except Exception:
            pass

        return list(patient_ids)

    def close(self):
        """Close HTTP session."""
        if self._session is not None:
            self._session.close()
            self._session = None


# Convenience function for quick setup
def create_fhir_backend(
    base_url: str,
    auth_token: Optional[str] = None,
) -> FHIRBackend:
    """
    Create a FHIR backend with minimal configuration.

    Args:
        base_url: FHIR server base URL
        auth_token: Optional Bearer token for authentication

    Returns:
        Configured FHIRBackend instance

    Example:
        backend = create_fhir_backend(
            "https://fhir.hospital.org/r4",
            auth_token="my-api-key"
        )
    """
    config = FHIRConfig(base_url=base_url, auth_token=auth_token)
    return FHIRBackend(config)
