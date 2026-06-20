from datetime import datetime
from types import SimpleNamespace

import pytest

import services.solana_listener as solana_listener
from services.socials_checker import SocialProfile, SocialsChecker


class FakeRedis:
    def __init__(self, *, fail_first_lpush: bool = False):
        self.fail_first_lpush = fail_first_lpush
        self.calls = []

    async def lpush(self, key, payload):
        self.calls.append(("lpush", key, payload))
        if self.fail_first_lpush:
            self.fail_first_lpush = False
            raise RuntimeError("max single record size exceeded")

    async def ltrim(self, key, start, stop):
        self.calls.append(("ltrim", key, start, stop))

    async def delete(self, key):
        self.calls.append(("delete", key))


def _listener_with_redis(redis_client):
    listener = object.__new__(solana_listener.SolanaListener)
    listener._redis_client = redis_client
    return listener


def _token_data():
    return SimpleNamespace(
        address="token",
        symbol="SOC",
        name="Social Token",
        mc_string="$100k",
        age_string="1h",
        age_minutes=60,
        telegram="https://t.me/social",
        twitter="https://x.com/social",
        website="https://social.example",
    )


def test_socials_checker_alerts_on_complete_basic_socials_when_enrichment_is_weak():
    checker = SocialsChecker()
    profile = SocialProfile(
        token_address="token",
        twitter_url="https://x.com/social",
        telegram_url="https://t.me/social",
        website_url="https://social.example",
        twitter_followers=0,
        has_verified_twitter=False,
        has_active_telegram=True,
        social_score=75,
        enhanced_score=15,
        checked_at=solana_listener.datetime.utcnow(),
    )

    assert checker.is_alertable_socials(profile) is True


def test_socials_checker_keeps_partial_basic_socials_quiet_without_enrichment():
    checker = SocialsChecker()
    profile = SocialProfile(
        token_address="token",
        twitter_url="https://x.com/social",
        telegram_url="https://t.me/social",
        website_url=None,
        twitter_followers=0,
        has_verified_twitter=False,
        has_active_telegram=True,
        social_score=55,
        enhanced_score=15,
        checked_at=solana_listener.datetime.utcnow(),
    )

    assert checker.is_alertable_socials(profile) is False


def test_socials_checker_returns_unalerted_alertable_profiles():
    checker = SocialsChecker()
    checker._profiles["token"] = SocialProfile(
        token_address="token",
        twitter_url="https://x.com/social",
        telegram_url="https://t.me/social",
        website_url="https://social.example",
        twitter_followers=0,
        has_verified_twitter=False,
        has_active_telegram=True,
        social_score=75,
        enhanced_score=15,
        checked_at=solana_listener.datetime.utcnow(),
    )

    profiles = checker.get_alertable_profiles(limit=1)

    assert [profile.token_address for profile in profiles] == ["token"]


def test_socials_checker_excludes_already_alerted_profiles_from_background_flush():
    checker = SocialsChecker()
    checker._profiles["token"] = SocialProfile(
        token_address="token",
        twitter_url="https://x.com/social",
        telegram_url="https://t.me/social",
        website_url="https://social.example",
        twitter_followers=0,
        has_verified_twitter=False,
        has_active_telegram=True,
        social_score=75,
        enhanced_score=15,
        checked_at=solana_listener.datetime.utcnow(),
    )
    checker.mark_alerted("token")

    assert checker.get_alertable_profiles(limit=1) == []



def test_socials_stats_do_not_promote_partial_profiles_to_alertable_or_log_strong(caplog):
    checker = SocialsChecker()
    checker._profiles["partial"] = SocialProfile(
        token_address="partial",
        twitter_url="https://x.com/partial",
        telegram_url="https://t.me/partial",
        website_url=None,
        twitter_followers=0,
        has_verified_twitter=False,
        has_active_telegram=True,
        social_score=55,
        enhanced_score=15,
        checked_at=solana_listener.datetime.utcnow(),
    )

    with caplog.at_level("INFO"):
        stats = checker.get_stats()

    assert stats["basic_socials"] == 1
    assert stats["alertable_socials"] == 0
    assert stats["strong_socials"] == 0
    assert "STRONG SOCIALS" not in caplog.text
@pytest.mark.asyncio
async def test_socials_queue_trims_after_push(monkeypatch):
    monkeypatch.setattr(solana_listener.settings, "socials_queue_max_length", 2, raising=False)
    redis = FakeRedis()

    await _listener_with_redis(redis)._send_to_socials_queue(_token_data(), "https://x.com/social")

    assert [call[:2] for call in redis.calls] == [
        ("lpush", "trench:socials:queue"),
        ("ltrim", "trench:socials:queue"),
    ]
    assert redis.calls[1] == ("ltrim", "trench:socials:queue", 0, 1)


@pytest.mark.asyncio
async def test_socials_queue_recovers_from_upstash_record_size_limit(monkeypatch):
    monkeypatch.setattr(solana_listener.settings, "socials_queue_max_length", 2, raising=False)
    redis = FakeRedis(fail_first_lpush=True)

    await _listener_with_redis(redis)._send_to_socials_queue(_token_data(), "https://x.com/social")

    assert [call[:2] for call in redis.calls] == [
        ("lpush", "trench:socials:queue"),
        ("delete", "trench:socials:queue"),
        ("lpush", "trench:socials:queue"),
        ("ltrim", "trench:socials:queue"),
    ]


def test_socials_stats_explain_profiles_that_are_not_alertable():
    checker = SocialsChecker()
    checker._profiles["partial"] = SocialProfile(
        token_address="partial",
        twitter_url="https://x.com/project",
        telegram_url=None,
        website_url=None,
        twitter_followers=0,
        has_verified_twitter=False,
        has_active_telegram=False,
        social_score=30,
        checked_at=datetime.utcnow(),
    )

    stats = checker.get_stats()

    assert stats["rejected_socials"] == 1
    assert stats["rejected_by_reason"] == {"partial_socials_below_threshold": 1}