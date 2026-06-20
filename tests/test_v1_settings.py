from config import Settings


def test_v1_settings_combines_comma_and_numbered_helius_keys():
    settings = Settings(
        helius_api_keys="helius-a,helius-b",
        helius_api_key_3="helius-c",
        helius_api_key_10="helius-j",
    )

    assert settings.helius_api_keys == ["helius-a", "helius-b", "helius-c", "helius-j"]