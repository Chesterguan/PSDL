#!/usr/bin/env python3
"""
PSDL Code Generation Tool

Generates code from specification files using Jinja2 templates:
- Python types from spec/schema.json (via datamodel-codegen)
- Operator metadata from spec/operators.yaml (via Jinja2)
- SQL templates from spec/operators.yaml (via Jinja2)
- Validation of implementations against spec

Usage:
    python tools/codegen.py --all              # Generate everything
    python tools/codegen.py --types            # Generate Python types only
    python tools/codegen.py --operators        # Generate operator metadata only
    python tools/codegen.py --sql              # Generate SQL templates only
    python tools/codegen.py --validate         # Validate implementations against spec
    python tools/codegen.py --check            # Check if regeneration needed (CI mode)
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("ERROR: jinja2 not installed. Install with: pip install jinja2")
    sys.exit(1)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SPEC_DIR = PROJECT_ROOT / "spec"
TEMPLATES_DIR = SPEC_DIR / "templates"
SRC_DIR = PROJECT_ROOT / "src" / "psdl"
GENERATED_DIR = SRC_DIR / "_generated"

# Spec files
SCHEMA_FILE = SPEC_DIR / "schema.json"
OPERATORS_FILE = SPEC_DIR / "operators.yaml"
VERSION_FILE = SPEC_DIR / "VERSION"

# Generated files
TYPES_FILE = GENERATED_DIR / "schema_types.py"
OPERATORS_META_FILE = GENERATED_DIR / "operators_meta.py"
SQL_TEMPLATES_FILE = GENERATED_DIR / "sql_templates.py"
CHECKSUM_FILE = GENERATED_DIR / ".checksums"

# Jinja2 templates
OPERATORS_META_TEMPLATE = "operators_meta.py.j2"
SQL_TEMPLATES_TEMPLATE = "sql_templates.py.j2"


def ensure_generated_dir() -> None:
    """Create _generated directory if it doesn't exist."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    # Create __init__.py
    init_file = GENERATED_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Auto-generated PSDL types and metadata. DO NOT EDIT."""\n')


def compute_checksum(file_path: Path) -> str:
    """Compute MD5 checksum of a file."""
    return hashlib.md5(file_path.read_bytes()).hexdigest()


def load_checksums() -> dict[str, str]:
    """Load existing checksums."""
    if CHECKSUM_FILE.exists():
        return json.loads(CHECKSUM_FILE.read_text())
    return {}


def save_checksums(checksums: dict[str, str]) -> None:
    """Save checksums to file."""
    CHECKSUM_FILE.write_text(json.dumps(checksums, indent=2))


def needs_regeneration() -> bool:
    """Check if any spec file has changed since last generation."""
    checksums = load_checksums()

    for spec_file in [SCHEMA_FILE, OPERATORS_FILE, VERSION_FILE]:
        if not spec_file.exists():
            print(f"  Missing spec file: {spec_file}")
            return True

        current = compute_checksum(spec_file)
        stored = checksums.get(spec_file.name)

        if current != stored:
            print(f"  Changed: {spec_file.name}")
            return True

    return False


def generate_types() -> bool:
    """Generate Python types from schema.json using datamodel-codegen."""
    print("Generating Python types from schema.json...")

    ensure_generated_dir()

    if not SCHEMA_FILE.exists():
        print(f"  ERROR: Schema file not found: {SCHEMA_FILE}")
        return False

    try:
        # Check if datamodel-codegen is available (try as module first)
        result = subprocess.run(
            [sys.executable, "-m", "datamodel_code_generator", "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("  ERROR: datamodel-code-generator not installed")
            print("  Install with: pip install datamodel-code-generator")
            return False
    except FileNotFoundError:
        print("  ERROR: datamodel-code-generator not installed")
        print("  Install with: pip install datamodel-code-generator")
        return False

    # Generate types using module invocation
    result = subprocess.run(
        [
            sys.executable, "-m", "datamodel_code_generator",
            "--input", str(SCHEMA_FILE),
            "--output", str(TYPES_FILE),
            "--input-file-type", "jsonschema",
            "--output-model-type", "dataclasses.dataclass",
            "--use-standard-collections",
            "--use-union-operator",
            "--target-python-version", "3.10",
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}")
        return False

    # Add header comment
    content = TYPES_FILE.read_text()
    header = f'''"""
Auto-generated Python types from spec/schema.json
Generated: {datetime.now().isoformat()}

DO NOT EDIT - Regenerate with: python tools/codegen.py --types
"""

'''
    TYPES_FILE.write_text(header + content)

    print(f"  Generated: {TYPES_FILE.relative_to(PROJECT_ROOT)}")
    return True


def load_operators_spec() -> dict[str, Any]:
    """Load and parse operators.yaml."""
    if not OPERATORS_FILE.exists():
        raise FileNotFoundError(f"Operators spec not found: {OPERATORS_FILE}")

    return yaml.safe_load(OPERATORS_FILE.read_text())


def get_jinja_env() -> Environment:
    """Create Jinja2 environment with templates directory."""
    if not TEMPLATES_DIR.exists():
        raise FileNotFoundError(f"Templates directory not found: {TEMPLATES_DIR}")

    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def generate_operators_meta() -> bool:
    """Generate operator metadata module from operators.yaml using Jinja2."""
    print("Generating operator metadata from operators.yaml...")

    ensure_generated_dir()

    try:
        spec = load_operators_spec()
    except Exception as e:
        print(f"  ERROR: Failed to load operators.yaml: {e}")
        return False

    try:
        env = get_jinja_env()
        template = env.get_template(OPERATORS_META_TEMPLATE)
    except Exception as e:
        print(f"  ERROR: Failed to load template {OPERATORS_META_TEMPLATE}: {e}")
        return False

    version = spec.get("version", "unknown")
    operators = spec.get("operators", {})
    windowed_ops = operators.get("windowed", {})
    pointwise_ops = operators.get("pointwise", {})

    # Render template
    content = template.render(
        timestamp=datetime.now().isoformat(),
        version=version,
        windowed_operators=windowed_ops,
        pointwise_operators=pointwise_ops,
    )

    OPERATORS_META_FILE.write_text(content)

    print(f"  Generated: {OPERATORS_META_FILE.relative_to(PROJECT_ROOT)}")
    print(f"    - {len(windowed_ops)} windowed operators")
    print(f"    - {len(pointwise_ops)} pointwise operators")

    return True


def generate_sql_templates() -> bool:
    """Generate SQL templates from operators.yaml using Jinja2."""
    print("Generating SQL templates from operators.yaml...")

    ensure_generated_dir()

    try:
        spec = load_operators_spec()
    except Exception as e:
        print(f"  ERROR: Failed to load operators.yaml: {e}")
        return False

    try:
        env = get_jinja_env()
        template = env.get_template(SQL_TEMPLATES_TEMPLATE)
    except Exception as e:
        print(f"  ERROR: Failed to load template {SQL_TEMPLATES_TEMPLATE}: {e}")
        return False

    operators = spec.get("operators", {})
    windowed_ops = operators.get("windowed", {})
    pointwise_ops = operators.get("pointwise", {})

    # Render template
    content = template.render(
        timestamp=datetime.now().isoformat(),
        windowed_operators=windowed_ops,
        pointwise_operators=pointwise_ops,
    )

    SQL_TEMPLATES_FILE.write_text(content)

    # Count operators with SQL support
    sql_windowed = sum(1 for op in windowed_ops.values()
                       if op.get("implementations", {}).get("postgresql")
                       and op["implementations"]["postgresql"] != "null")
    sql_pointwise = sum(1 for op in pointwise_ops.values()
                        if op.get("implementations", {}).get("postgresql")
                        and op["implementations"]["postgresql"] != "null")

    print(f"  Generated: {SQL_TEMPLATES_FILE.relative_to(PROJECT_ROOT)}")
    print(f"    - {sql_windowed} windowed SQL templates")
    print(f"    - {sql_pointwise} pointwise SQL templates")

    return True


def validate_implementations() -> bool:
    """Validate that implementations match the spec."""
    print("Validating implementations against spec...")

    try:
        spec = load_operators_spec()
    except Exception as e:
        print(f"  ERROR: Failed to load spec: {e}")
        return False

    operators = spec.get("operators", {})
    windowed_ops = set(operators.get("windowed", {}).keys())
    pointwise_ops = set(operators.get("pointwise", {}).keys())

    # Add aliases
    for name, meta in operators.get("windowed", {}).items():
        windowed_ops.update(meta.get("aliases", []))
    for name, meta in operators.get("pointwise", {}).items():
        pointwise_ops.update(meta.get("aliases", []))

    spec_ops = windowed_ops | pointwise_ops

    # Check Python implementation
    operators_py = SRC_DIR / "operators.py"
    if not operators_py.exists():
        print(f"  WARNING: operators.py not found")
        return True

    content = operators_py.read_text()

    # Find OPERATORS dict
    if "OPERATORS = {" in content:
        match = re.search(r'OPERATORS\s*=\s*\{([^}]+)\}', content, re.DOTALL)
        if match:
            impl_ops = set(re.findall(r'"(\w+)":', match.group(1)))

            missing = spec_ops - impl_ops
            extra = impl_ops - spec_ops

            if missing:
                print(f"  WARNING: Missing implementations: {sorted(missing)}")
            if extra:
                print(f"  INFO: Extra implementations (not in spec): {sorted(extra)}")

            if not missing:
                print(f"  OK: All {len(spec_ops)} spec operators have implementations")
                return True
            return False

    print("  WARNING: Could not parse OPERATORS dict")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PSDL Code Generation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--all", action="store_true", help="Generate everything")
    parser.add_argument("--types", action="store_true", help="Generate Python types from schema.json")
    parser.add_argument("--operators", action="store_true", help="Generate operator metadata")
    parser.add_argument("--sql", action="store_true", help="Generate SQL templates from operators.yaml")
    parser.add_argument("--validate", action="store_true", help="Validate implementations")
    parser.add_argument("--check", action="store_true", help="Check if regeneration needed (CI mode)")

    args = parser.parse_args()

    # Default to --all if no options specified
    if not any([args.all, args.types, args.operators, args.sql, args.validate, args.check]):
        args.all = True

    success = True
    checksums = {}

    print(f"PSDL Code Generator")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"  Spec: {SPEC_DIR}")
    print(f"  Templates: {TEMPLATES_DIR}")
    print()

    if args.check:
        print("Checking if regeneration needed...")
        if needs_regeneration():
            print("  Regeneration needed!")
            return 1
        else:
            print("  Up to date.")
            return 0

    if args.all or args.types:
        if not generate_types():
            success = False
        else:
            checksums[SCHEMA_FILE.name] = compute_checksum(SCHEMA_FILE)

    if args.all or args.operators:
        if not generate_operators_meta():
            success = False
        else:
            checksums[OPERATORS_FILE.name] = compute_checksum(OPERATORS_FILE)

    if args.all or args.sql:
        if not generate_sql_templates():
            success = False
        else:
            checksums[OPERATORS_FILE.name] = compute_checksum(OPERATORS_FILE)

    if args.all or args.validate:
        if not validate_implementations():
            success = False

    # Save checksums if generation was successful
    if success and checksums:
        if VERSION_FILE.exists():
            checksums[VERSION_FILE.name] = compute_checksum(VERSION_FILE)
        save_checksums(checksums)
        print()
        print("Checksums saved.")

    print()
    if success:
        print("Done!")
        return 0
    else:
        print("Completed with warnings/errors.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
