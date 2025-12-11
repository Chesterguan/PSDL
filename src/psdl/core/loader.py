"""
PSDL Loader - YAML and JSON loading utilities.

This module provides functions for loading PSDL scenario files
from disk or string content.
"""

from pathlib import Path
from typing import Any, Dict, Union

import yaml


def load_yaml(content: str) -> Dict[str, Any]:
    """
    Load YAML content from a string.

    Args:
        content: YAML string content

    Returns:
        Parsed YAML as a dictionary

    Raises:
        yaml.YAMLError: If the YAML is invalid
    """
    return yaml.safe_load(content)


def load_yaml_file(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Load YAML content from a file.

    Args:
        filepath: Path to the YAML file

    Returns:
        Parsed YAML as a dictionary

    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the YAML is invalid
    """
    with open(filepath, "r") as f:
        return yaml.safe_load(f)


def load_json(content: str) -> Dict[str, Any]:
    """
    Load JSON content from a string.

    Args:
        content: JSON string content

    Returns:
        Parsed JSON as a dictionary

    Raises:
        json.JSONDecodeError: If the JSON is invalid
    """
    import json

    return json.loads(content)


def load_json_file(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Load JSON content from a file.

    Args:
        filepath: Path to the JSON file

    Returns:
        Parsed JSON as a dictionary

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the JSON is invalid
    """
    import json

    with open(filepath, "r") as f:
        return json.load(f)
