"""
PSDL Data Backends

This module provides backend connectors for various clinical data sources:
- InMemoryBackend: For testing and development
- OMOPBackend: For OMOP CDM databases (v5.4)
- FHIRBackend: For FHIR R4 servers
"""

from .fhir import FHIRBackend, FHIRConfig, create_fhir_backend
from .omop import OMOPBackend, OMOPConfig

__all__ = [
    "OMOPBackend",
    "OMOPConfig",
    "FHIRBackend",
    "FHIRConfig",
    "create_fhir_backend",
]
