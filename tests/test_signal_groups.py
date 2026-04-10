"""Tests for signal_groups (RFC-0009)."""

import pytest

from psdl.core.ir import ClinicalDomain, SignalGroup


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
