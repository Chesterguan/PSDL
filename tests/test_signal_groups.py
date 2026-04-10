"""Tests for signal_groups (RFC-0009)."""

import pytest

from psdl.core.ir import ClinicalDomain, PSDLScenario, Signal, SignalGroup


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
