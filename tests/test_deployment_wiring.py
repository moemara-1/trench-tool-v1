from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v2_compose_starts_the_v2_alert_worker():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "v2-backend:" in compose
    assert "main_v2:app" in compose


def test_env_template_includes_recovered_topic_configuration():
    env_template = (ROOT / ".env.example").read_text(encoding="utf-8")
    required_keys = {
        "TELEGRAM_ETH_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID",
        "TELEGRAM_DEV_HELD_TOPIC_ID",
        "TELEGRAM_STRONG_LAUNCH_TOPIC_ID",
        "TELEGRAM_FEEDBACK_TOPIC_ID",
    }

    missing = {key for key in required_keys if f"{key}=" not in env_template}
    assert missing == set()


def test_env_template_lists_each_recovered_topic_once():
    entries = [line.strip() for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()]
    recovered_keys = {
        "TELEGRAM_FEEDBACK_TOPIC_ID",
        "TELEGRAM_DEV_HELD_TOPIC_ID",
        "TELEGRAM_STRONG_LAUNCH_TOPIC_ID",
        "TELEGRAM_ETH_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_BIG_FRESHIES_TOPIC_ID",
        "TELEGRAM_ETH_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID",
        "TELEGRAM_BASE_DEPLOYS_TOPIC_ID",
    }

    for key in recovered_keys:
        assert sum(line.startswith(f"{key}=") for line in entries) == 1


def test_recovery_command_updates_the_compose_environment_file():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "TRENCH_V2_ENV=.env TRENCH_V1_ENV=.env python scripts/reconcile_v2_topics.py" in readme


def test_v2_docker_health_check_uses_dependency_free_liveness():
    compose_files = (
        ROOT / "docker-compose.yml",
        ROOT / "docker-compose.v2.yml",
    )
    api = (ROOT / "trench_v2" / "api.py").read_text(encoding="utf-8")

    assert all(
        'http://localhost:8001/live' in compose_file.read_text(encoding="utf-8")
        for compose_file in compose_files
    )
    assert '@app.get("/live")' in api