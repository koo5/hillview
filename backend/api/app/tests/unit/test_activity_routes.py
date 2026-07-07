"""Unit tests for activity feed visibility helpers."""
import pytest

from activity_routes import (
	get_visible_activity_statuses,
	include_authorized_activity_photos,
)


def test_include_authorized_activity_photos_disabled_by_default(monkeypatch):
	monkeypatch.delenv("ACTIVITY_SHOW_AUTHORIZED_PHOTOS", raising=False)
	assert include_authorized_activity_photos() is False
	assert get_visible_activity_statuses() == ("completed",)


@pytest.mark.parametrize("truthy_value", ["true", "1", "yes"])
def test_include_authorized_activity_photos_accepts_truthy_values(monkeypatch, truthy_value):
	monkeypatch.setenv("ACTIVITY_SHOW_AUTHORIZED_PHOTOS", truthy_value)
	assert include_authorized_activity_photos() is True
	assert get_visible_activity_statuses() == ("completed", "authorized")


def test_include_authorized_activity_photos_rejects_falsey_values(monkeypatch):
	monkeypatch.setenv("ACTIVITY_SHOW_AUTHORIZED_PHOTOS", "false")
	assert include_authorized_activity_photos() is False
	assert get_visible_activity_statuses() == ("completed",)
