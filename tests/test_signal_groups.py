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


class TestPublicAPI:
    def test_import_signal_group_from_psdl_package(self):
        """SignalGroup is re-exported at the package root."""
        import psdl

        assert hasattr(psdl, "SignalGroup")
        assert psdl.SignalGroup is SignalGroup
        assert "SignalGroup" in psdl.__all__
