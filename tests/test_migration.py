"""Tests for version 1 to version 2 config-entry migration helpers."""

from custom_components.movistar_rft8115vw.migration import (
    migrate_options_v1,
    migrate_tracker_unique_id_v1,
)


def test_legacy_interval_is_renamed() -> None:
    """The version 1 interval key becomes scan_interval."""
    assert migrate_options_v1({"interval_seconds": 60, "consider_home": 180}) == {
        "scan_interval": 60,
        "consider_home": 180,
    }


def test_options_are_clamped_to_version_2_limits() -> None:
    """Too-short intervals are raised; grace is never shorter than polling."""
    assert migrate_options_v1({"interval_seconds": 10, "consider_home": 5}) == {
        "scan_interval": 30,
        "consider_home": 30,
    }


def test_missing_options_use_defaults() -> None:
    """An entry without options gets the version 2 defaults."""
    assert migrate_options_v1({}) == {"scan_interval": 300, "consider_home": 600}


def test_tracker_unique_id_is_upper_cased() -> None:
    """Lower-case MAC unique IDs are converted; upper-case ones are unchanged."""
    assert migrate_tracker_unique_id_v1("aa:bb:cc:dd:ee:01") == "AA:BB:CC:DD:EE:01"
    assert migrate_tracker_unique_id_v1("AA:BB:CC:DD:EE:01") is None
