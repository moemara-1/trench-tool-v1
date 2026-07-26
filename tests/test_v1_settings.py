from config import Settings


def test_v1_settings_combines_comma_and_numbered_helius_keys():
    settings = Settings(
        helius_api_keys="helius-a,helius-b",
        helius_api_key_3="helius-c",
        helius_api_key_10="helius-j",
    )

    assert settings.helius_api_keys == ["helius-a", "helius-b", "helius-c", "helius-j"]

def test_v1_best_signals_defaults_require_cross_source_confluence():
    settings = Settings()

    assert settings.best_signals_min_confluence_sources == 2
    assert settings.best_signals_confluence_window_minutes == 45
    assert settings.best_signals_min_confluence_component_score == 90


def test_v1_strong_launch_topic_is_disabled_without_explicit_wiring():
    settings = Settings()

    assert settings.telegram_strong_launch_topic_id == 0
