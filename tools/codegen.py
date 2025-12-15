#!/usr/bin/env python3
"""
PSDL Code Generation Tool

Generates code from specification files using industry-standard tools:
- Python types from spec/schema.json (via datamodel-codegen)
- Operator metadata from spec/operators.yaml (via Jinja2)
- SQL templates from spec/operators.yaml (via Jinja2)
- AST types from spec/ast-nodes.yaml (via Jinja2)
- Lark Transformer from spec/ast-nodes.yaml grammar_mappings (via Jinja2)
- Conformance tests from spec/conformance/*.yaml
- Validation of implementations against spec

Usage:
    python tools/codegen.py --all              # Generate everything
    python tools/codegen.py --types            # Generate Python types from schema.json
    python tools/codegen.py --operators        # Generate operator metadata
    python tools/codegen.py --sql              # Generate SQL templates
    python tools/codegen.py --ast              # Generate AST types from ast-nodes.yaml
    python tools/codegen.py --transformer      # Generate Lark Transformer from ast-nodes.yaml
    python tools/codegen.py --conformance      # Generate conformance tests from spec/conformance/
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
from typing import Any, Dict

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
OPERATORS_FILE = SPEC_DIR / "operators.yaml"  # Legacy monolithic file
AST_NODES_FILE = SPEC_DIR / "ast-nodes.yaml"
VERSION_FILE = SPEC_DIR / "VERSION"

# Split operators structure (RFC-0006)
OPERATORS_DIR = SPEC_DIR / "operators"
OPERATORS_SIGNATURES_FILE = OPERATORS_DIR / "signatures.yaml"
OPERATORS_BACKENDS_DIR = OPERATORS_DIR / "backends"

# Generated files
TYPES_FILE = GENERATED_DIR / "schema_types.py"
OPERATORS_META_FILE = GENERATED_DIR / "operators_meta.py"
SQL_TEMPLATES_FILE = GENERATED_DIR / "sql_templates.py"
AST_TYPES_FILE = GENERATED_DIR / "ast_types.py"
TRANSFORMER_FILE = GENERATED_DIR / "transformer.py"
CONFORMANCE_FILE = GENERATED_DIR / "conformance_tests.py"
CHECKSUM_FILE = GENERATED_DIR / ".checksums"

# Conformance spec directory
CONFORMANCE_DIR = SPEC_DIR / "conformance"

# Jinja2 templates
OPERATORS_META_TEMPLATE = "operators_meta.py.j2"
SQL_TEMPLATES_TEMPLATE = "sql_templates.py.j2"
AST_TYPES_TEMPLATE = "ast_types.py.j2"
TRANSFORMER_TEMPLATE = "transformer.py.j2"


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


def load_checksums() -> Dict[str, str]:
    """Load existing checksums."""
    if CHECKSUM_FILE.exists():
        return json.loads(CHECKSUM_FILE.read_text())
    return {}


def save_checksums(checksums: Dict[str, str]) -> None:
    """Save checksums to file."""
    CHECKSUM_FILE.write_text(json.dumps(checksums, indent=2))


def needs_regeneration() -> bool:
    """Check if any spec file has changed since last generation."""
    checksums = load_checksums()

    for spec_file in [SCHEMA_FILE, OPERATORS_FILE, AST_NODES_FILE, VERSION_FILE]:
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
    # Use Python 3.9 compatible syntax (min supported by datamodel-codegen)
    # Note: We don't use --use-standard-collections or --use-union-operator
    # to maintain Python 3.8 compatibility in the generated code
    result = subprocess.run(
        [
            sys.executable, "-m", "datamodel_code_generator",
            "--input", str(SCHEMA_FILE),
            "--output", str(TYPES_FILE),
            "--input-file-type", "jsonschema",
            "--output-model-type", "dataclasses.dataclass",
            "--target-python-version", "3.9",
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


def load_operators_spec() -> Dict[str, Any]:
    """
    Load and parse operators spec.

    Supports two structures:
    1. Split structure (RFC-0006): spec/operators/signatures.yaml + backends/
    2. Legacy monolithic: spec/operators.yaml

    Returns unified spec format for code generation.
    """
    # Try split structure first (RFC-0006)
    if OPERATORS_SIGNATURES_FILE.exists():
        signatures = yaml.safe_load(OPERATORS_SIGNATURES_FILE.read_text())

        # Load backends
        backends = {}
        if OPERATORS_BACKENDS_DIR.exists():
            for backend_file in OPERATORS_BACKENDS_DIR.glob("*.yaml"):
                dialect = backend_file.stem  # e.g., "postgresql"
                backends[dialect] = yaml.safe_load(backend_file.read_text())

        # Merge backends into operators
        return _merge_operators_with_backends(signatures, backends)

    # Fallback to legacy monolithic file
    if not OPERATORS_FILE.exists():
        raise FileNotFoundError(f"Operators spec not found: {OPERATORS_FILE}")

    return yaml.safe_load(OPERATORS_FILE.read_text())


def _merge_operators_with_backends(
    signatures: Dict[str, Any], backends: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Merge operator signatures with backend implementations.

    Transforms flat signature structure into nested structure expected by templates:
    - null_handling -> semantics.null_handling
    - min_points -> semantics.min_points
    """
    result = signatures.copy()

    operators = result.get("operators", {})

    # Transform and merge windowed operators
    for op_name, op_spec in operators.get("windowed", {}).items():
        # Create nested semantics structure for template compatibility
        if "semantics" not in op_spec:
            op_spec["semantics"] = {}
        if "null_handling" in op_spec:
            op_spec["semantics"]["null_handling"] = op_spec["null_handling"]
        if "min_points" in op_spec:
            op_spec["semantics"]["min_points"] = op_spec["min_points"]

        # Initialize implementations
        if "implementations" not in op_spec:
            op_spec["implementations"] = {}

    # Transform and merge pointwise operators
    for op_name, op_spec in operators.get("pointwise", {}).items():
        # Create nested semantics structure for template compatibility
        if "semantics" not in op_spec:
            op_spec["semantics"] = {}
        if "null_handling" in op_spec:
            op_spec["semantics"]["null_handling"] = op_spec["null_handling"]

        # Initialize implementations
        if "implementations" not in op_spec:
            op_spec["implementations"] = {}

    # Add implementations from backends
    for dialect, backend in backends.items():
        templates = backend.get("templates", {})

        # Merge into windowed operators
        for op_name, op_spec in operators.get("windowed", {}).items():
            if op_name in templates:
                op_spec["implementations"][dialect] = templates[op_name]

        # Merge into pointwise operators
        for op_name, op_spec in operators.get("pointwise", {}).items():
            if op_name in templates:
                op_spec["implementations"][dialect] = templates[op_name]

    return result


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


def load_ast_nodes_spec() -> Dict[str, Any]:
    """Load and parse ast-nodes.yaml."""
    if not AST_NODES_FILE.exists():
        raise FileNotFoundError(f"AST nodes spec not found: {AST_NODES_FILE}")

    return yaml.safe_load(AST_NODES_FILE.read_text())


def generate_ast_types() -> bool:
    """Generate AST types from ast-nodes.yaml using Jinja2."""
    print("Generating AST types from ast-nodes.yaml...")

    ensure_generated_dir()

    try:
        spec = load_ast_nodes_spec()
    except Exception as e:
        print(f"  ERROR: Failed to load ast-nodes.yaml: {e}")
        return False

    try:
        env = get_jinja_env()
        template = env.get_template(AST_TYPES_TEMPLATE)
    except Exception as e:
        print(f"  ERROR: Failed to load template {AST_TYPES_TEMPLATE}: {e}")
        return False

    version = spec.get("version", "unknown")
    primitives = spec.get("primitives", {})
    nodes = spec.get("nodes", {})
    type_aliases = spec.get("type_aliases", {})

    # Render template
    content = template.render(
        timestamp=datetime.now().isoformat(),
        version=version,
        primitives=primitives,
        nodes=nodes,
        type_aliases=type_aliases,
    )

    AST_TYPES_FILE.write_text(content)

    print(f"  Generated: {AST_TYPES_FILE.relative_to(PROJECT_ROOT)}")
    print(f"    - {len(primitives)} primitive types (enums)")
    print(f"    - {len(nodes)} AST node classes")
    print(f"    - {len(type_aliases)} type aliases")

    return True


def generate_transformer() -> bool:
    """Generate Lark Transformer from ast-nodes.yaml grammar_mappings using Jinja2."""
    print("Generating Lark Transformer from ast-nodes.yaml grammar_mappings...")

    ensure_generated_dir()

    try:
        spec = load_ast_nodes_spec()
    except Exception as e:
        print(f"  ERROR: Failed to load ast-nodes.yaml: {e}")
        return False

    grammar_mappings = spec.get("grammar_mappings", {})
    if not grammar_mappings:
        print("  WARNING: No grammar_mappings found in ast-nodes.yaml")
        return False

    try:
        env = get_jinja_env()
        template = env.get_template(TRANSFORMER_TEMPLATE)
    except Exception as e:
        print(f"  ERROR: Failed to load template {TRANSFORMER_TEMPLATE}: {e}")
        return False

    version = spec.get("version", "unknown")

    # Render template
    content = template.render(
        timestamp=datetime.now().isoformat(),
        version=version,
        grammar_mappings=grammar_mappings,
    )

    TRANSFORMER_FILE.write_text(content)

    # Count mapping types
    inline_count = sum(1 for m in grammar_mappings.values() if m.get("inline"))
    variadic_count = sum(1 for m in grammar_mappings.values() if m.get("mode") == "variadic")
    conditional_count = sum(1 for m in grammar_mappings.values() if m.get("mode") == "conditional")
    list_count = len(grammar_mappings) - inline_count - variadic_count - conditional_count

    print(f"  Generated: {TRANSFORMER_FILE.relative_to(PROJECT_ROOT)}")
    print(f"    - {len(grammar_mappings)} transformer methods total")
    print(f"    - {inline_count} inline methods (@v_args)")
    print(f"    - {list_count} list-based methods")
    print(f"    - {variadic_count} variadic methods")
    print(f"    - {conditional_count} conditional methods")

    return True


def generate_conformance_tests() -> bool:
    """Generate pytest conformance tests from spec/conformance/*.yaml."""
    print("Generating conformance tests from spec/conformance/...")

    ensure_generated_dir()

    if not CONFORMANCE_DIR.exists():
        print("  No conformance specs found (spec/conformance/ does not exist)")
        return True

    conformance_files = list(CONFORMANCE_DIR.glob("*.yaml"))
    if not conformance_files:
        print("  No conformance spec files found")
        return True

    # Collect all test cases
    test_cases = []
    for spec_file in conformance_files:
        spec = yaml.safe_load(spec_file.read_text())
        test_cases.extend(_extract_conformance_tests(spec, spec_file.stem))

    # Generate test file
    content = _render_conformance_tests(test_cases)
    CONFORMANCE_FILE.write_text(content)

    # Count test types
    valid_count = sum(1 for t in test_cases if t["test_type"] == "valid_parse")
    invalid_count = sum(1 for t in test_cases if t["test_type"] == "invalid_parse")
    comparison_rejected = sum(1 for t in test_cases if t["test_type"] == "trend_comparison_rejected")

    print(f"  Generated: {CONFORMANCE_FILE.relative_to(PROJECT_ROOT)}")
    print(f"    - {len(test_cases)} test cases total")
    print(f"    - {valid_count} valid parse tests")
    print(f"    - {invalid_count} invalid parse tests")
    print(f"    - {comparison_rejected} comparison rejection tests")

    return True


def _extract_conformance_tests(spec: Dict[str, Any], source: str) -> list:
    """Extract test cases from a conformance spec."""
    tests = []

    # Extract windowed operator tests
    for op_name, op_spec in spec.get("windowed_operators", {}).items():
        for test in op_spec.get("valid_parse", []):
            tests.append({
                "source": source,
                "operator": op_name,
                "test_type": "valid_parse",
                "expr": test["expr"],
                "expected": test.get("expected", {}),
                "description": f"Parse valid {op_name} expression",
            })
        for test in op_spec.get("invalid_parse", []):
            tests.append({
                "source": source,
                "operator": op_name,
                "test_type": "invalid_parse",
                "expr": test["expr"],
                "reason": test.get("reason", "Should fail to parse"),
                "description": f"Reject invalid {op_name} expression",
            })
        for test in op_spec.get("trend_comparison_rejected", []):
            tests.append({
                "source": source,
                "operator": op_name,
                "test_type": "trend_comparison_rejected",
                "expr": test["expr"],
                "reason": test.get("reason", "Comparison not allowed in trend"),
                "description": f"Reject {op_name} with comparison (v0.3)",
            })

    # Extract pointwise operator tests
    for op_name, op_spec in spec.get("pointwise_operators", {}).items():
        for test in op_spec.get("valid_parse", []):
            tests.append({
                "source": source,
                "operator": op_name,
                "test_type": "valid_parse",
                "expr": test["expr"],
                "expected": test.get("expected", {}),
                "description": f"Parse valid {op_name} expression",
            })
        for test in op_spec.get("invalid_parse", []):
            tests.append({
                "source": source,
                "operator": op_name,
                "test_type": "invalid_parse",
                "expr": test["expr"],
                "reason": test.get("reason", "Should fail to parse"),
                "description": f"Reject invalid {op_name} expression",
            })

    # Extract arithmetic tests
    for test in spec.get("arithmetic", {}).get("valid_parse", []):
        tests.append({
            "source": source,
            "operator": "arithmetic",
            "test_type": "valid_parse",
            "expr": test["expr"],
            "expected": {"type": test.get("expected_type", "ArithExpr")},
            "description": test.get("description", "Parse arithmetic expression"),
        })

    # Extract logic tests
    for test in spec.get("logic", {}).get("valid_parse", []):
        tests.append({
            "source": source,
            "operator": "logic",
            "test_type": "valid_parse",
            "expr": test["expr"],
            "expected": {
                "type": test.get("expected_type"),
                "terms": test.get("expected_terms", []),
                "operators": test.get("expected_operators", []),
            },
            "description": test.get("description", "Parse logic expression"),
        })

    for test in spec.get("logic", {}).get("comparison_in_logic", []):
        tests.append({
            "source": source,
            "operator": "logic_comparison",
            "test_type": "valid_parse",
            "expr": test["expr"],
            "expected": {
                "type": test.get("expected_type", "ComparisonExpr"),
                "operator": test.get("expected_operator"),
            },
            "description": test.get("description", "Parse comparison in logic"),
        })

    return tests


def check_conformance_coverage() -> bool:
    """Check that all operators in spec have conformance test coverage."""
    print("Checking conformance test coverage...")

    # Load operator spec
    try:
        op_spec = load_operators_spec()
    except Exception as e:
        print(f"  ERROR: Failed to load operators.yaml: {e}")
        return False

    operators = op_spec.get("operators", {})
    spec_windowed = set(operators.get("windowed", {}).keys())
    spec_pointwise = set(operators.get("pointwise", {}).keys())

    # Add aliases
    for name, meta in operators.get("windowed", {}).items():
        spec_windowed.update(meta.get("aliases", []))
    for name, meta in operators.get("pointwise", {}).items():
        spec_pointwise.update(meta.get("aliases", []))

    # Load conformance tests
    if not CONFORMANCE_DIR.exists():
        print("  ERROR: spec/conformance/ directory not found")
        return False

    conformance_files = list(CONFORMANCE_DIR.glob("*.yaml"))
    if not conformance_files:
        print("  ERROR: No conformance spec files found")
        return False

    tested_windowed = set()
    tested_pointwise = set()

    for spec_file in conformance_files:
        spec = yaml.safe_load(spec_file.read_text())

        # Collect tested operators
        for op_name in spec.get("windowed_operators", {}).keys():
            tested_windowed.add(op_name)
        for op_name in spec.get("pointwise_operators", {}).keys():
            tested_pointwise.add(op_name)

    # Check coverage
    missing_windowed = spec_windowed - tested_windowed
    missing_pointwise = spec_pointwise - tested_pointwise
    extra_windowed = tested_windowed - spec_windowed
    extra_pointwise = tested_pointwise - spec_pointwise

    success = True

    if missing_windowed:
        print(f"  MISSING: Windowed operators without tests: {sorted(missing_windowed)}")
        success = False
    if missing_pointwise:
        print(f"  MISSING: Pointwise operators without tests: {sorted(missing_pointwise)}")
        success = False

    if extra_windowed:
        print(f"  INFO: Extra windowed tests (not in spec): {sorted(extra_windowed)}")
    if extra_pointwise:
        print(f"  INFO: Extra pointwise tests (not in spec): {sorted(extra_pointwise)}")

    # Summary
    total_spec = len(spec_windowed) + len(spec_pointwise)
    total_tested = len(tested_windowed) + len(tested_pointwise)
    coverage = (total_tested / total_spec * 100) if total_spec > 0 else 0

    print(f"  Coverage: {total_tested}/{total_spec} operators ({coverage:.0f}%)")
    print(f"    - Windowed: {len(tested_windowed)}/{len(spec_windowed)}")
    print(f"    - Pointwise: {len(tested_pointwise)}/{len(spec_pointwise)}")

    if success:
        print("  OK: All spec operators have conformance tests")

    return success


def _render_conformance_tests(test_cases: list) -> str:
    """Render conformance tests as pytest file."""
    timestamp = datetime.now().isoformat()

    lines = [
        '"""',
        f"Auto-generated conformance tests from spec/conformance/",
        f"Generated: {timestamp}",
        "",
        "DO NOT EDIT - Regenerate with: python tools/codegen.py --conformance",
        '"""',
        "",
        "import pytest",
        "from psdl.expression_parser import (",
        "    PSDLExpressionParser,",
        "    PSDLExpressionError,",
        "    extract_terms,",
        "    extract_operators,",
        "    TrendExpression,",
        "    ArithExpr,",
        "    AndExpr,",
        "    OrExpr,",
        "    NotExpr,",
        "    TermRef,",
        "    ComparisonExpr,",
        ")",
        "",
        "",
        "@pytest.fixture",
        "def parser():",
        '    """Create parser instance for tests."""',
        "    return PSDLExpressionParser()",
        "",
        "",
        "# " + "=" * 70,
        "# VALID PARSE TESTS",
        "# " + "=" * 70,
        "",
    ]

    # Group valid parse tests
    valid_tests = [t for t in test_cases if t["test_type"] == "valid_parse"]
    for i, test in enumerate(valid_tests):
        test_name = f"test_valid_{test['operator']}_{i}"
        lines.append(f"def {test_name}(parser):")
        lines.append(f'    """{test["description"]}"""')

        if test["operator"] in ["logic", "logic_comparison"]:
            lines.append(f'    result = parser.parse_logic({repr(test["expr"])})')
        else:
            lines.append(f'    result = parser.parse_trend({repr(test["expr"])})')

        lines.append("    assert result is not None")

        # Add specific assertions based on expected values
        expected = test.get("expected", {})
        expected_type = expected.get("type")

        # Different assertion paths for trend vs logic types
        if test["operator"] in ["logic", "logic_comparison"]:
            # Logic expressions - check type and operators
            if expected_type:
                lines.append(f'    assert isinstance(result, {expected_type})')
            if expected.get("operator"):
                # For ComparisonExpr, operator is on the result directly
                lines.append(f'    assert result.operator == {repr(expected["operator"])}')
            if expected.get("terms"):
                lines.append(f'    assert set(extract_terms(result)) == {set(expected["terms"])}')
        else:
            # Trend expressions - check temporal attributes
            if expected.get("operator"):
                lines.append(f'    assert result.temporal.operator == {repr(expected["operator"])}')
            if expected.get("signal"):
                lines.append(f'    assert result.temporal.signal == {repr(expected["signal"])}')
            if expected.get("window_value"):
                lines.append(f'    assert result.temporal.window.value == {expected["window_value"]}')
            if expected.get("window_unit"):
                lines.append(f'    assert result.temporal.window.unit == {repr(expected["window_unit"])}')
            if expected_type:
                lines.append(f'    assert isinstance(result, {expected_type})')

        lines.append("")
        lines.append("")

    # Invalid parse tests
    lines.append("# " + "=" * 70)
    lines.append("# INVALID PARSE TESTS")
    lines.append("# " + "=" * 70)
    lines.append("")

    invalid_tests = [t for t in test_cases if t["test_type"] == "invalid_parse"]
    for i, test in enumerate(invalid_tests):
        test_name = f"test_invalid_{test['operator']}_{i}"
        lines.append(f"def {test_name}(parser):")
        lines.append(f'    """{test["description"]}: {test.get("reason", "")}"""')
        lines.append("    with pytest.raises(PSDLExpressionError):")

        if test["operator"] in ["logic", "logic_comparison"]:
            lines.append(f'        parser.parse_logic({repr(test["expr"])})')
        else:
            lines.append(f'        parser.parse_trend({repr(test["expr"])})')

        lines.append("")
        lines.append("")

    # Comparison rejection tests (v0.3 STRICT)
    lines.append("# " + "=" * 70)
    lines.append("# V0.3 STRICT COMPARISON REJECTION TESTS")
    lines.append("# " + "=" * 70)
    lines.append("# v0.3 STRICT: Comparisons in trend expressions MUST cause parse errors")
    lines.append("# Comparisons belong ONLY in the Logic layer (ComparisonExpr)")
    lines.append("")

    comparison_tests = [t for t in test_cases if t["test_type"] == "trend_comparison_rejected"]
    for i, test in enumerate(comparison_tests):
        test_name = f"test_comparison_in_trend_rejected_{test['operator']}_{i}"
        lines.append(f"def {test_name}(parser):")
        lines.append(f'    """{test["description"]}: {test.get("reason", "")}"""')
        lines.append(f'    # v0.3 STRICT: Comparisons in trend expressions MUST be rejected')
        lines.append(f'    with pytest.raises(PSDLExpressionError):')
        lines.append(f'        parser.parse_trend({repr(test["expr"])})')
        lines.append("")
        lines.append("")

    return "\n".join(lines)


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
    parser.add_argument("--ast", action="store_true", help="Generate AST types from ast-nodes.yaml")
    parser.add_argument("--transformer", action="store_true", help="Generate Lark Transformer from ast-nodes.yaml")
    parser.add_argument("--conformance", action="store_true", help="Generate conformance tests from spec/conformance/")
    parser.add_argument("--validate", action="store_true", help="Validate implementations")
    parser.add_argument("--check", action="store_true", help="Check if regeneration needed (CI mode)")

    args = parser.parse_args()

    # Default to --all if no options specified
    if not any([args.all, args.types, args.operators, args.sql, args.ast, args.transformer, args.conformance, args.validate, args.check]):
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

    if args.all or args.ast:
        if not generate_ast_types():
            success = False
        else:
            checksums[AST_NODES_FILE.name] = compute_checksum(AST_NODES_FILE)

    if args.all or args.transformer:
        if not generate_transformer():
            success = False
        else:
            checksums[AST_NODES_FILE.name] = compute_checksum(AST_NODES_FILE)

    if args.all or args.conformance:
        if not generate_conformance_tests():
            success = False
        # Always check coverage when generating conformance tests
        if not check_conformance_coverage():
            success = False

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
