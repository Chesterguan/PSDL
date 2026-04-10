"""Tests for signal_groups (RFC-0009)."""

import pytest

from psdl.core.ir import ClinicalDomain, PSDLScenario, Signal, SignalGroup
from psdl.core.parser import PSDLParseError, PSDLParser


class TestSignalGroupDataclass:
    def test_domain_level_group(self):
        """Domain-level group has domain set, members None."""
        group = SignalGroup(
            name="all_labs",
            description="All lab results",
            domain=ClinicalDomain.LABORATORY,
        )
        assert group.name == "all_labs"
        assert group.domain == ClinicalDomain.LABORATORY
        assert group.members is None

    def test_custom_panel(self):
        """Custom panel has members list, domain None."""
        group = SignalGroup(
            name="renal_panel",
            description="Renal monitoring",
            members=["creatinine", "hemoglobin"],
        )
        assert group.name == "renal_panel"
        assert group.domain is None
        assert group.members == ["creatinine", "hemoglobin"]

    def test_both_domain_and_members_raises(self):
        """Setting both domain and members raises ValueError."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            SignalGroup(
                name="hybrid",
                description="Bad",
                domain=ClinicalDomain.LABORATORY,
                members=["creatinine"],
            )

    def test_neither_domain_nor_members_raises(self):
        """Setting neither domain nor members raises ValueError."""
        with pytest.raises(ValueError, match="must have either"):
            SignalGroup(name="empty", description="Bad")

    def test_empty_members_list_raises(self):
        """Empty members list is treated as no members and raises."""
        with pytest.raises(ValueError, match="must have either"):
            SignalGroup(name="empty_list", description="Bad", members=[])

    def test_domain_with_empty_members_raises(self):
        """Domain set together with an empty members list is still rejected."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            SignalGroup(
                name="bad",
                description="Bad",
                domain=ClinicalDomain.LABORATORY,
                members=[],
            )


def _minimal_scenario_kwargs():
    """Build the minimum required PSDLScenario kwargs for these tests."""
    return dict(
        name="test",
        version="1.0.0",
        description="test scenario",
        population=None,
        signals={"creatinine": Signal(name="creatinine", ref="creatinine")},
        trends={},
        logic={},
    )


class TestPSDLScenarioSignalGroupsField:
    def test_default_is_empty_dict(self):
        """PSDLScenario.signal_groups defaults to empty dict."""
        scenario = PSDLScenario(**_minimal_scenario_kwargs())
        assert scenario.signal_groups == {}

    def test_populated_field(self):
        """PSDLScenario.signal_groups can be populated at construction."""
        kwargs = _minimal_scenario_kwargs()
        kwargs["signal_groups"] = {
            "renal": SignalGroup(
                name="renal",
                description="Renal panel",
                members=["creatinine"],
            )
        }
        scenario = PSDLScenario(**kwargs)
        assert "renal" in scenario.signal_groups
        assert scenario.signal_groups["renal"].members == ["creatinine"]

    def test_validate_accepts_valid_members(self):
        """validate() returns no group errors when members reference defined signals."""
        kwargs = _minimal_scenario_kwargs()
        kwargs["signal_groups"] = {
            "renal": SignalGroup(
                name="renal",
                description="Renal panel",
                members=["creatinine"],
            )
        }
        scenario = PSDLScenario(**kwargs)
        errors = scenario.validate()
        assert not any("signal group" in e.lower() for e in errors)

    def test_validate_rejects_unknown_member(self):
        """validate() returns an error naming the unknown signal."""
        kwargs = _minimal_scenario_kwargs()
        kwargs["signal_groups"] = {
            "renal": SignalGroup(
                name="renal",
                description="Renal panel",
                members=["creatinine", "nonexistent"],
            )
        }
        scenario = PSDLScenario(**kwargs)
        errors = scenario.validate()
        matching = [e for e in errors if "nonexistent" in e and "renal" in e]
        assert len(matching) == 1

    def test_validate_skips_member_check_for_domain_group(self):
        """Domain-only groups don't trigger the member-validation loop."""
        kwargs = _minimal_scenario_kwargs()
        kwargs["signal_groups"] = {
            "all_labs": SignalGroup(
                name="all_labs",
                description="All labs",
                domain=ClinicalDomain.LABORATORY,
            )
        }
        scenario = PSDLScenario(**kwargs)
        errors = scenario.validate()
        assert not any("signal group" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Parser integration tests
# ---------------------------------------------------------------------------

MINIMAL_YAML = """
scenario: test
version: "1.0.0"
description: "test scenario"

signals:
  creatinine:
    ref: creatinine
    unit: mg/dL
  hemoglobin:
    ref: hemoglobin
    unit: g/dL

trends:
  cr_current:
    type: float
    unit: mg/dL
    expr: last(creatinine)
  hgb_current:
    type: float
    unit: g/dL
    expr: last(hemoglobin)

logic:
  cr_high:
    when: cr_current >= 4.0
    description: "High creatinine"
"""


class TestParserSignalGroups:
    """Parser-level tests for signal_groups YAML parsing (RFC-0009)."""

    def test_parse_no_signal_groups(self):
        """Scenarios without signal_groups parse normally."""
        parser = PSDLParser()
        scenario = parser.parse_string(MINIMAL_YAML)
        assert scenario.signal_groups == {}

    def test_parse_domain_level_group(self):
        """Parse a domain-level signal group."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  all_labs:
    domain: laboratory
    description: "All lab results"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert "all_labs" in scenario.signal_groups
        group = scenario.signal_groups["all_labs"]
        assert group.domain == ClinicalDomain.LABORATORY
        assert group.members is None
        assert group.description == "All lab results"

    def test_parse_custom_panel(self):
        """Parse a custom signal group with members."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  renal_panel:
    members: [creatinine, hemoglobin]
    description: "Renal monitoring"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert "renal_panel" in scenario.signal_groups
        group = scenario.signal_groups["renal_panel"]
        assert group.domain is None
        assert group.members == ["creatinine", "hemoglobin"]
        assert group.description == "Renal monitoring"

    def test_parse_multiple_groups_mixed(self):
        """Parse multiple signal groups of both types."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  all_labs:
    domain: laboratory
    description: "All labs"
  renal_panel:
    members: [creatinine, hemoglobin]
    description: "Renal panel"
  all_meds:
    domain: medication
    description: "All medications"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert len(scenario.signal_groups) == 3
        assert scenario.signal_groups["all_labs"].domain == ClinicalDomain.LABORATORY
        assert scenario.signal_groups["all_meds"].domain == ClinicalDomain.MEDICATION
        assert scenario.signal_groups["renal_panel"].members == ["creatinine", "hemoglobin"]

    def test_parse_all_clinical_domains(self):
        """All ClinicalDomain enum values are accepted in domain-level groups."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  g_labs:
    domain: laboratory
    description: "Labs"
  g_vitals:
    domain: vital_sign
    description: "Vitals"
  g_conditions:
    domain: condition
    description: "Conditions"
  g_meds:
    domain: medication
    description: "Meds"
  g_procs:
    domain: procedure
    description: "Procedures"
  g_obs:
    domain: observation
    description: "Observations"
  g_demo:
    domain: demographic
    description: "Demographics"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert len(scenario.signal_groups) == 7
        assert scenario.signal_groups["g_labs"].domain == ClinicalDomain.LABORATORY
        assert scenario.signal_groups["g_vitals"].domain == ClinicalDomain.VITAL_SIGN
        assert scenario.signal_groups["g_conditions"].domain == ClinicalDomain.CONDITION
        assert scenario.signal_groups["g_meds"].domain == ClinicalDomain.MEDICATION
        assert scenario.signal_groups["g_procs"].domain == ClinicalDomain.PROCEDURE
        assert scenario.signal_groups["g_obs"].domain == ClinicalDomain.OBSERVATION
        assert scenario.signal_groups["g_demo"].domain == ClinicalDomain.DEMOGRAPHIC

    def test_parse_invalid_member_fails(self):
        """Custom group referencing an unknown signal fails at parse time."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad_panel:
    members: [creatinine, nonexistent_signal]
    description: "Bad panel"
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="nonexistent_signal"):
            parser.parse_string(yaml)

    def test_parse_missing_description_fails(self):
        """Group without description raises parse error."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  no_desc:
    domain: laboratory
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="description"):
            parser.parse_string(yaml)

    def test_parse_both_domain_and_members_fails(self):
        """Group with both domain and members raises parse error (Phase 1)."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  hybrid:
    domain: laboratory
    members: [creatinine]
    description: "Not allowed in Phase 1"
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="mutually exclusive"):
            parser.parse_string(yaml)

    def test_parse_neither_domain_nor_members_fails(self):
        """Group with neither domain nor members raises parse error."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  empty:
    description: "Has neither"
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="must have either"):
            parser.parse_string(yaml)

    def test_parse_invalid_domain_value_fails(self):
        """Group with invalid domain value raises parse error."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad_domain:
    domain: not_a_real_domain
    description: "Invalid domain"
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="unknown domain"):
            parser.parse_string(yaml)

    def test_parse_members_not_list_fails(self):
        """Group with non-list members raises parse error."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad_type:
    members: creatinine
    description: "Members should be a list"
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="must be a list"):
            parser.parse_string(yaml)

    def test_parse_non_dict_group_spec_fails(self):
        """Group specified as a non-dict raises parse error."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad_spec: "this is a string not a dict"
"""
        )
        parser = PSDLParser()
        with pytest.raises(PSDLParseError, match="Invalid signal group"):
            parser.parse_string(yaml)

    def test_parse_empty_signal_groups_section(self):
        """Empty signal_groups section parses to empty dict."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups: {}
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert scenario.signal_groups == {}

    def test_parse_null_signal_groups_section(self):
        """Null signal_groups section parses to empty dict."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert scenario.signal_groups == {}


class TestSignalGroupsRoundTrip:
    """End-to-end tests exercising the full parse + validate flow."""

    def test_realistic_perioperative_cohort(self):
        """A realistic cohort scenario with multiple domain-level and custom groups."""
        yaml = """
scenario: Perioperative_Cohort
version: "0.1.0"
description: "Perioperative surgical cohort"

signals:
  creatinine:
    ref: creatinine
    unit: mg/dL
  hemoglobin:
    ref: hemoglobin
    unit: g/dL
  lactate:
    ref: lactate
    unit: mmol/L
  inr:
    ref: international_normalized_ratio
    unit: ratio
  platelets:
    ref: platelet_count
    unit: "x10^3/uL"

trends:
  cr_current:
    type: float
    unit: mg/dL
    expr: last(creatinine)
  hgb_current:
    type: float
    unit: g/dL
    expr: last(hemoglobin)
  lactate_current:
    type: float
    unit: mmol/L
    expr: last(lactate)

logic:
  cr_critical:
    when: cr_current >= 4.0
    severity: critical
    description: "Critical creatinine"
  hgb_low:
    when: hgb_current <= 7.0
    severity: high
    description: "Low hemoglobin"
  lactate_high:
    when: lactate_current >= 4.0
    severity: high
    description: "High lactate"

signal_groups:
  all_labs:
    domain: laboratory
    description: "All lab results for cohort patients"
  all_meds:
    domain: medication
    description: "All medication administrations"
  all_procedures:
    domain: procedure
    description: "All ICD and CPT procedures"
  all_vitals:
    domain: vital_sign
    description: "All vitals including height and weight"
  renal_panel:
    members: [creatinine, hemoglobin]
    description: "Renal monitoring subset"
  coag_panel:
    members: [inr, platelets]
    description: "Coagulation monitoring"
  perfusion_panel:
    members: [lactate, hemoglobin]
    description: "Tissue perfusion indicators"
"""
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)

        # 4 domain-level + 3 custom groups
        assert len(scenario.signal_groups) == 7

        # Domain-level groups
        assert scenario.signal_groups["all_labs"].domain == ClinicalDomain.LABORATORY
        assert scenario.signal_groups["all_meds"].domain == ClinicalDomain.MEDICATION
        assert scenario.signal_groups["all_procedures"].domain == ClinicalDomain.PROCEDURE
        assert scenario.signal_groups["all_vitals"].domain == ClinicalDomain.VITAL_SIGN

        # Custom panels
        assert scenario.signal_groups["renal_panel"].members == ["creatinine", "hemoglobin"]
        assert scenario.signal_groups["coag_panel"].members == ["inr", "platelets"]
        assert scenario.signal_groups["perfusion_panel"].members == ["lactate", "hemoglobin"]

        # Validation passes (no errors)
        errors = scenario.validate()
        group_errors = [e for e in errors if "signal group" in e.lower()]
        assert group_errors == []

    def test_backward_compatibility_scenarios_without_groups(self):
        """Existing scenarios without signal_groups still parse and validate."""
        parser = PSDLParser()
        scenario = parser.parse_string(MINIMAL_YAML)
        assert scenario.signal_groups == {}
        # Should not raise on validate
        errors = scenario.validate()
        group_errors = [e for e in errors if "signal group" in e.lower()]
        assert group_errors == []


MINIMAL_YAML = """
scenario: test_scenario
version: "1.0.0"
description: "test scenario"

signals:
  creatinine:
    ref: creatinine
    unit: mg/dL
  hemoglobin:
    ref: hemoglobin
    unit: g/dL

trends:
  cr_current:
    expr: last(creatinine)
    description: "Current creatinine"
  hgb_current:
    expr: last(hemoglobin)
    description: "Current hemoglobin"

logic:
  high_cr:
    when: cr_current >= 4.0
    description: "High creatinine"
"""


class TestParserSignalGroups:
    def test_parse_without_signal_groups(self):
        """Scenarios without signal_groups parse with an empty dict."""
        parser = PSDLParser()
        scenario = parser.parse_string(MINIMAL_YAML)
        assert scenario.signal_groups == {}

    def test_parse_domain_group(self):
        """Parse a single domain-level group."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  all_labs:
    domain: laboratory
    description: "All lab results"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert "all_labs" in scenario.signal_groups
        group = scenario.signal_groups["all_labs"]
        assert group.domain == ClinicalDomain.LABORATORY
        assert group.members is None
        assert group.description == "All lab results"

    def test_parse_custom_panel(self):
        """Parse a single custom panel."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  renal_panel:
    members: [creatinine, hemoglobin]
    description: "Renal panel"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        group = scenario.signal_groups["renal_panel"]
        assert group.domain is None
        assert group.members == ["creatinine", "hemoglobin"]

    def test_parse_multiple_groups(self):
        """Parse a mix of domain-level and custom groups."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  all_labs:
    domain: laboratory
    description: "All labs"
  renal_panel:
    members: [creatinine, hemoglobin]
    description: "Renal panel"
"""
        )
        parser = PSDLParser()
        scenario = parser.parse_string(yaml)
        assert len(scenario.signal_groups) == 2

    def test_parse_missing_description_fails(self):
        """Missing description raises PSDLParseError."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  no_desc:
    domain: laboratory
"""
        )
        with pytest.raises(PSDLParseError, match="description"):
            PSDLParser().parse_string(yaml)

    def test_parse_domain_and_members_fails(self):
        """Both domain and members raises PSDLParseError."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  hybrid:
    domain: laboratory
    members: [creatinine]
    description: "Bad"
"""
        )
        with pytest.raises(PSDLParseError, match="mutually exclusive"):
            PSDLParser().parse_string(yaml)

    def test_parse_neither_domain_nor_members_fails(self):
        """Neither domain nor members raises PSDLParseError."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  empty:
    description: "Bad"
"""
        )
        with pytest.raises(PSDLParseError, match="must have either"):
            PSDLParser().parse_string(yaml)

    def test_parse_invalid_domain_fails(self):
        """Unknown domain value raises PSDLParseError."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad:
    domain: not_a_domain
    description: "Bad"
"""
        )
        with pytest.raises(PSDLParseError, match="unknown domain"):
            PSDLParser().parse_string(yaml)

    def test_parse_members_not_a_list_fails(self):
        """Non-list members raises PSDLParseError."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad:
    members: "creatinine"
    description: "Bad"
"""
        )
        with pytest.raises(PSDLParseError, match="must be a list"):
            PSDLParser().parse_string(yaml)

    def test_parse_unknown_member_signal_fails_at_parse_time(self):
        """Groups referencing unknown signals raise PSDLParseError at parse time."""
        yaml = (
            MINIMAL_YAML
            + """
signal_groups:
  bad:
    members: [creatinine, nonexistent_signal]
    description: "Bad"
"""
        )
        with pytest.raises(PSDLParseError, match="nonexistent_signal"):
            PSDLParser().parse_string(yaml)
