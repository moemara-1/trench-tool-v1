from types import SimpleNamespace

from services import freshies_wizard
from services.freshies_wizard import FreshiesWizard


def test_freshies_wizard_has_no_general_topic_fallback(monkeypatch):
    monkeypatch.setattr(
        freshies_wizard,
        "settings",
        SimpleNamespace(telegram_wizard_topic_id=0, telegram_patterns_topic_id=0),
    )

    assert FreshiesWizard()._destination_topic_id() is None


def test_freshies_wizard_prefers_wizard_topic_then_patterns(monkeypatch):
    monkeypatch.setattr(
        freshies_wizard,
        "settings",
        SimpleNamespace(telegram_wizard_topic_id=66, telegram_patterns_topic_id=61),
    )

    assert FreshiesWizard()._destination_topic_id() == 66

    monkeypatch.setattr(
        freshies_wizard,
        "settings",
        SimpleNamespace(telegram_wizard_topic_id=0, telegram_patterns_topic_id=61),
    )

    assert FreshiesWizard()._destination_topic_id() == 61


def test_freshies_wizard_can_mirror_to_patterns_topic(monkeypatch):
    monkeypatch.setattr(
        freshies_wizard,
        "settings",
        SimpleNamespace(telegram_wizard_topic_id=66, telegram_patterns_topic_id=61),
    )

    assert FreshiesWizard()._destination_topic_ids() == [66, 61]
