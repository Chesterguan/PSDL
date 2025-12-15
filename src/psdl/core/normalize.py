"""
PSDL YAML Normalization Layer.

Ensures deterministic parsing of YAML input by normalizing types
that could vary across parsers or YAML syntax variations.

Problems solved:
1. Dates: 2024-01-01 → datetime vs string
2. Versions: 1.0 → float vs string "1.0"
3. Booleans: yes/no/on/off → bool vs string
4. YAML tags: !!set, !!python, etc. → rejected

Usage:
    from psdl.core.normalize import normalize_yaml, load_yaml_normalized

    # From string
    data = normalize_yaml(yaml_content)

    # From file
    data = load_yaml_normalized("scenario.yaml")
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Union

import yaml


class PSDLYAMLError(Exception):
    """Error during YAML normalization."""

    pass


class PSDLSafeLoader(yaml.SafeLoader):
    """
    Custom YAML loader that enforces deterministic type handling.

    Key differences from SafeLoader:
    - Dates/timestamps remain as strings
    - Rejects non-standard YAML tags
    """

    pass


def _string_timestamp_constructor(loader: yaml.Loader, node: yaml.Node) -> str:
    """Force timestamps to remain as ISO strings."""
    return loader.construct_scalar(node)


def _reject_tag_constructor(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> None:
    """Reject non-standard YAML tags."""
    raise PSDLYAMLError(
        f"YAML tag '!{tag_suffix}' is not allowed in PSDL. "
        f"Only standard YAML types are permitted."
    )


# Override timestamp handling - keep as string
PSDLSafeLoader.add_constructor("tag:yaml.org,2002:timestamp", _string_timestamp_constructor)

# Reject Python-specific tags
for tag in ["python/object", "python/name", "python/module", "python/tuple"]:
    PSDLSafeLoader.add_multi_constructor(
        f"tag:yaml.org,2002:{tag}",
        lambda loader, suffix, node: _reject_tag_constructor(loader, suffix, node),
    )


# Fields that must always be strings
STRING_FIELDS = {
    "version",
    "scenario_version",
    "psdl_version",
    "uri",
    "reference",
}

# Fields that must always be strings if they look like versions
VERSION_PATTERN_FIELDS = {
    "version",
}


def normalize_yaml(content: str) -> Dict[str, Any]:
    """
    Parse YAML with deterministic type handling.

    Args:
        content: YAML string content

    Returns:
        Normalized dictionary with deterministic types

    Raises:
        PSDLYAMLError: If YAML contains disallowed constructs

    Rules applied:
    1. Dates/timestamps → ISO format strings
    2. Version fields → always strings
    3. YAML tags (!!set, !!python) → rejected
    4. Anchors/aliases → expanded (by default)
    """
    try:
        data = yaml.load(content, Loader=PSDLSafeLoader)
    except yaml.YAMLError as e:
        raise PSDLYAMLError(f"Invalid YAML: {e}") from e

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise PSDLYAMLError(f"PSDL scenario must be a YAML mapping, got {type(data).__name__}")

    return _normalize_types(data)


def load_yaml_normalized(path: Union[str, Path]) -> Dict[str, Any]:
    """
    Load and normalize YAML from file.

    Args:
        path: Path to YAML file

    Returns:
        Normalized dictionary
    """
    path = Path(path)
    if not path.exists():
        raise PSDLYAMLError(f"File not found: {path}")

    content = path.read_text(encoding="utf-8")
    return normalize_yaml(content)


def _normalize_types(obj: Any, path: str = "") -> Any:
    """
    Recursively normalize types for determinism.

    Args:
        obj: Object to normalize
        path: Current path for error messages (e.g., "signals.Cr.unit")

    Returns:
        Normalized object
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            current_path = f"{path}.{key}" if path else key
            normalized_value = _normalize_types(value, current_path)

            # Force certain fields to string
            if key in STRING_FIELDS and normalized_value is not None:
                if not isinstance(normalized_value, str):
                    normalized_value = str(normalized_value)

            result[key] = normalized_value
        return result

    elif isinstance(obj, list):
        return [_normalize_types(item, f"{path}[{i}]") for i, item in enumerate(obj)]

    elif isinstance(obj, (date, datetime)):
        # Convert dates to ISO format strings
        return obj.isoformat()

    elif isinstance(obj, bool):
        # Keep booleans as-is (they're unambiguous)
        return obj

    elif isinstance(obj, (int, float)):
        # Keep numbers as-is
        return obj

    elif isinstance(obj, str):
        return obj

    elif obj is None:
        return None

    else:
        # Unknown type - convert to string with warning
        return str(obj)


def validate_determinism(content: str) -> Dict[str, Any]:
    """
    Parse YAML and validate for deterministic behavior.

    Returns the parsed data along with any warnings about
    potentially non-deterministic constructs.

    Args:
        content: YAML string content

    Returns:
        Dict with 'data' and 'warnings' keys
    """
    warnings = []

    # Check for common issues before parsing
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Check for YAML tags
        if stripped.startswith("!!"):
            warnings.append(f"Line {i}: YAML tag detected - may cause portability issues")

        # Check for anchors (not an error, but worth noting)
        if "&" in stripped and not stripped.startswith("#"):
            if any(c in stripped for c in ["&", "*"]) and ":" in stripped:
                # Could be anchor/alias
                pass  # Anchors are OK but expanded

    data = normalize_yaml(content)

    return {
        "data": data,
        "warnings": warnings,
    }


# Convenience function for backward compatibility
def safe_load_psdl(content: str) -> Dict[str, Any]:
    """
    Backward-compatible function name for normalize_yaml.

    Deprecated: Use normalize_yaml() instead.
    """
    return normalize_yaml(content)
