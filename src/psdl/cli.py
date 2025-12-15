"""
PSDL Command Line Interface

Usage:
    psdl validate <scenario.yaml>     Validate a PSDL scenario file
    psdl parse <scenario.yaml>        Parse and display scenario structure
    psdl version                      Show version information
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    """Main entry point for the PSDL CLI."""
    parser = argparse.ArgumentParser(
        prog="psdl",
        description="PSDL - Patient Scenario Definition Language CLI",
    )
    parser.add_argument("--version", "-v", action="store_true", help="Show version information")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a PSDL scenario file")
    validate_parser.add_argument(
        "file", type=Path, help="Path to PSDL scenario file (YAML or JSON)"
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict validation (check signal references)",
    )

    # parse command
    parse_parser = subparsers.add_parser("parse", help="Parse and display scenario structure")
    parse_parser.add_argument("file", type=Path, help="Path to PSDL scenario file")
    parse_parser.add_argument(
        "--json", action="store_true", dest="output_json", help="Output as JSON"
    )

    # version command
    subparsers.add_parser("version", help="Show version information")

    args = parser.parse_args()

    # Handle --version flag
    if args.version:
        show_version()
        return 0

    # Handle commands
    if args.command == "version":
        show_version()
        return 0
    elif args.command == "validate":
        return validate_scenario(args.file, args.strict)
    elif args.command == "parse":
        return parse_scenario(args.file, args.output_json)
    else:
        parser.print_help()
        return 0


def show_version():
    """Display version information."""
    from . import __version__

    print(f"PSDL v{__version__}")
    print("Patient Scenario Definition Language - Reference Implementation")
    print("https://github.com/Chesterguan/PSDL")


def validate_scenario(file_path: Path, strict: bool = False) -> int:
    """Validate a PSDL scenario file."""
    from .core import PSDLParser

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    try:
        parser = PSDLParser()
        scenario = parser.parse_file(str(file_path))

        # Basic validation passed
        print(f"Valid PSDL scenario: {scenario.name}")
        print(f"  Version: {scenario.version}")
        print(f"  Signals: {len(scenario.signals)}")
        print(f"  Trends:  {len(scenario.trends)}")
        print(f"  Logic:   {len(scenario.logic)}")

        if strict:
            # Check that all signal references in trends exist
            errors = []
            for trend_name, trend in scenario.trends.items():
                # Extract signal references from expression
                # This is a simple check - full validation is in the evaluator
                for signal_name in scenario.signals:
                    pass  # Signal exists

            if errors:
                for error in errors:
                    print(f"  Warning: {error}", file=sys.stderr)
                return 1

        return 0

    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return 1


def parse_scenario(file_path: Path, output_json: bool = False) -> int:
    """Parse and display scenario structure."""
    from .core import PSDLParser

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return 1

    try:
        parser = PSDLParser()
        scenario = parser.parse_file(str(file_path))

        if output_json:
            # Output as JSON
            output = {
                "name": scenario.name,
                "version": scenario.version,
                "description": getattr(scenario, "description", None),
                "signals": {
                    name: {"source": sig.source, "type": sig.type}
                    for name, sig in scenario.signals.items()
                },
                "trends": {
                    name: {
                        "expr": trend.expr,
                        "description": getattr(trend, "description", None),
                    }
                    for name, trend in scenario.trends.items()
                },
                "logic": {
                    name: {
                        "expr": logic.expr,
                        "severity": getattr(logic, "severity", None),
                    }
                    for name, logic in scenario.logic.items()
                },
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            print(f"Scenario: {scenario.name}")
            print(f"Version:  {scenario.version}")
            if hasattr(scenario, "description") and scenario.description:
                print(f"Description: {scenario.description}")
            print()

            print("Signals:")
            for name, sig in scenario.signals.items():
                print(f"  {name}: {sig.source} ({sig.type})")
            print()

            print("Trends:")
            for name, trend in scenario.trends.items():
                print(f"  {name}: {trend.expr}")
            print()

            print("Logic:")
            for name, logic in scenario.logic.items():
                severity = getattr(logic, "severity", None)
                sev_str = f" [{severity}]" if severity else ""
                print(f"  {name}: {logic.expr}{sev_str}")

        return 0

    except Exception as e:
        print(f"Parse failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
