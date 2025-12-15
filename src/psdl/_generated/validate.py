"""
PSDL Schema Validation Utilities.

This module provides optional JSON Schema validation for PSDL scenarios.
Validation is performed against spec/schema.json before parsing.

Usage:
    from psdl._generated.validate import validate_yaml, ValidationError

    # Validate YAML string against schema
    try:
        validate_yaml(yaml_content)
    except ValidationError as e:
        print(f"Schema validation failed: {e}")

    # Validate YAML file
    validate_yaml(yaml_content, source="scenario.yaml")

Architecture Notes (RFC-0006):
==============================
Schema validation is OPTIONAL but recommended for:
- CI/CD pipelines (strict mode)
- IDE integration (real-time validation)
- API endpoints (input validation)

The validation layer sits between:
    YAML Input → [Schema Validation] → Parser → IR Types
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

# Schema file location (relative to this file)
_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent / "spec" / "schema.json"


class ValidationError(Exception):
    """Raised when schema validation fails."""

    def __init__(
        self,
        message: str,
        errors: Optional[List[Dict[str, Any]]] = None,
        source: Optional[str] = None,
    ):
        self.message = message
        self.errors = errors or []
        self.source = source
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message with details."""
        parts = [self.message]
        if self.source:
            parts.append(f"Source: {self.source}")
        if self.errors:
            parts.append("Errors:")
            for error in self.errors[:5]:  # Limit to 5 errors
                if isinstance(error, dict):
                    path = error.get("path", "")
                    msg = error.get("message", str(error))
                    parts.append(f"  - {path}: {msg}")
                else:
                    parts.append(f"  - {error}")
            if len(self.errors) > 5:
                parts.append(f"  ... and {len(self.errors) - 5} more errors")
        return "\n".join(parts)


def load_schema() -> Dict[str, Any]:
    """Load the PSDL JSON Schema."""
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH, "r") as f:
        return json.load(f)


def validate_yaml(
    content: str,
    source: Optional[str] = None,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Validate YAML content against the PSDL schema.

    Args:
        content: YAML content string
        source: Optional source file path for error messages
        schema: Optional pre-loaded schema (for performance)

    Returns:
        Parsed YAML as dict (if valid)

    Raises:
        ValidationError: If schema validation fails
        yaml.YAMLError: If YAML parsing fails
    """
    # Parse YAML first
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValidationError(f"YAML parsing failed: {e}", source=source)

    if not isinstance(data, dict):
        raise ValidationError("YAML must be a mapping (dict)", source=source)

    # Try JSON Schema validation if jsonschema is available
    try:
        import jsonschema

        if schema is None:
            schema = load_schema()

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))

        if errors:
            error_details = [
                {
                    "path": ".".join(str(p) for p in e.absolute_path),
                    "message": e.message,
                }
                for e in errors
            ]
            raise ValidationError(
                f"Schema validation failed with {len(errors)} error(s)",
                errors=error_details,
                source=source,
            )

    except ImportError:
        # jsonschema not installed, skip validation
        pass

    return data


def validate_file(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Validate a PSDL YAML file against the schema.

    Args:
        filepath: Path to YAML file

    Returns:
        Parsed YAML as dict (if valid)

    Raises:
        ValidationError: If schema validation fails
        FileNotFoundError: If file doesn't exist
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    content = path.read_text()
    return validate_yaml(content, source=str(filepath))


def is_schema_validation_available() -> bool:
    """Check if JSON Schema validation is available."""
    try:
        import jsonschema  # noqa: F401

        return True
    except ImportError:
        return False


# Export types for type hints
__all__ = [
    "ValidationError",
    "validate_yaml",
    "validate_file",
    "load_schema",
    "is_schema_validation_available",
]
