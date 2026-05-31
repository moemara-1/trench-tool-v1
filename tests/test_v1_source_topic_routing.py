from types import SimpleNamespace

import services.solana_listener as solana_listener


def test_optional_v1_source_topics_do_not_fallback_to_freshies(monkeypatch):
    monkeypatch.setattr(
        solana_listener,
        "settings",
        SimpleNamespace(
            telegram_freshies_topic_id=111,
            telegram_good_creator_topic_id=0,
            telegram_socials_topic_id=0,
            telegram_strong_launch_topic_id=0,
            telegram_dev_held_topic_id=0,
        ),
    )

    assert solana_listener.good_creator_topic_id() is None
    assert solana_listener.socials_topic_id() is None
    assert solana_listener.strong_launch_topic_id() is None
    assert solana_listener.dev_held_topic_id() is None


def test_optional_v1_source_topics_use_dedicated_topic_ids(monkeypatch):
    monkeypatch.setattr(
        solana_listener,
        "settings",
        SimpleNamespace(
            telegram_freshies_topic_id=111,
            telegram_good_creator_topic_id=222,
            telegram_socials_topic_id=333,
            telegram_strong_launch_topic_id=444,
            telegram_dev_held_topic_id=555,
        ),
    )

    assert solana_listener.good_creator_topic_id() == 222
    assert solana_listener.socials_topic_id() == 333
    assert solana_listener.strong_launch_topic_id() == 444
    assert solana_listener.dev_held_topic_id() == 555
