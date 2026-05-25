from types import SimpleNamespace

from services import pattern_detector
from services.pattern_detector import PatternDetector


def test_pattern_detector_has_no_general_topic_fallback(monkeypatch):
    monkeypatch.setattr(
        pattern_detector,
        "settings",
        SimpleNamespace(telegram_patterns_topic_id=0),
    )

    assert PatternDetector()._destination_topic_id() is None


def test_pattern_detector_uses_patterns_topic(monkeypatch):
    monkeypatch.setattr(
        pattern_detector,
        "settings",
        SimpleNamespace(telegram_patterns_topic_id=61),
    )

    assert PatternDetector()._destination_topic_id() == 61
