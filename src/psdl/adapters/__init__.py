"""
PSDL Data Adapters

This module provides data adapters for various clinical data sources:
- InMemoryBackend: For testing and development (in evaluator.py)
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
