"""
Built-in PSDL example scenarios.

These scenarios are bundled with the package and can be loaded directly:

    from psdl.examples import get_scenario, list_scenarios

    # List available scenarios
    print(list_scenarios())

    # Load a specific scenario
    scenario = get_scenario("aki_detection")
"""

from pathlib import Path
from typing import List

# Get the directory containing example YAML files
_EXAMPLES_DIR = Path(__file__).parent


def list_scenarios() -> List[str]:
    """
    List all available built-in scenarios.

    Returns:
        List of scenario names (without .yaml extension)

    Example:
        >>> from psdl.examples import list_scenarios
        >>> print(list_scenarios())
        ['aki_detection', 'hyperkalemia_detection', 'lactic_acidosis', ...]
    """
    return sorted([f.stem for f in _EXAMPLES_DIR.glob("*.yaml")])


def get_scenario_path(name: str) -> Path:
    """
    Get the file path for a built-in scenario.

    Args:
        name: Scenario name (with or without .yaml extension)

    Returns:
        Path to the scenario YAML file

    Raises:
        FileNotFoundError: If scenario doesn't exist

    Example:
        >>> from psdl.examples import get_scenario_path
        >>> path = get_scenario_path("aki_detection")
        >>> print(path)
    """
    if not name.endswith(".yaml"):
        name = f"{name}.yaml"

    path = _EXAMPLES_DIR / name
    if not path.exists():
        available = list_scenarios()
        raise FileNotFoundError(f"Scenario '{name}' not found. Available scenarios: {available}")
    return path


def get_scenario(name: str):
    """
    Load and parse a built-in scenario.

    Args:
        name: Scenario name (e.g., "aki_detection", "sepsis_screening")

    Returns:
        PSDLScenario object ready for evaluation

    Example:
        >>> from psdl.examples import get_scenario
        >>> scenario = get_scenario("aki_detection")
        >>> print(scenario.name)
        'AKI_Detection'
    """
    from ..core import PSDLParser

    path = get_scenario_path(name)
    parser = PSDLParser()
    return parser.parse_file(str(path))


def get_scenario_yaml(name: str) -> str:
    """
    Get the raw YAML content of a built-in scenario.

    Args:
        name: Scenario name

    Returns:
        YAML content as string

    Example:
        >>> from psdl.examples import get_scenario_yaml
        >>> yaml_content = get_scenario_yaml("aki_detection")
        >>> print(yaml_content[:100])
    """
    path = get_scenario_path(name)
    return path.read_text()


# Convenience aliases for common scenarios
def get_aki_scenario():
    """Load the AKI (Acute Kidney Injury) detection scenario."""
    return get_scenario("aki_detection")


def get_sepsis_scenario():
    """Load the Sepsis screening scenario."""
    return get_scenario("sepsis_screening")


def get_hyperkalemia_scenario():
    """Load the Hyperkalemia detection scenario."""
    return get_scenario("hyperkalemia_detection")


def get_lactic_acidosis_scenario():
    """Load the Lactic Acidosis detection scenario."""
    return get_scenario("lactic_acidosis")


__all__ = [
    "list_scenarios",
    "get_scenario_path",
    "get_scenario",
    "get_scenario_yaml",
    "get_aki_scenario",
    "get_sepsis_scenario",
    "get_hyperkalemia_scenario",
    "get_lactic_acidosis_scenario",
]
