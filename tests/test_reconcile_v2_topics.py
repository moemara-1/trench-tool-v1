from scripts.reconcile_v2_topics import TELEGRAM_TOPIC_COLORS, WANTED_TOPICS


def test_reconcile_topic_plan_creates_restored_specialty_topics():
    assert WANTED_TOPICS["TELEGRAM_BEST_SIGNALS_TOPIC_ID"].title == "Best Signals"
    assert WANTED_TOPICS["TELEGRAM_BEST_WALLETS_WEEK_TOPIC_ID"].title == "Best Wallets Week"
    assert WANTED_TOPICS["TELEGRAM_BEST_WALLETS_MONTH_TOPIC_ID"].title == "Best Wallets Month"
    assert WANTED_TOPICS["TELEGRAM_BEST_WALLETS_YEAR_TOPIC_ID"].title == "Best Wallets Year"
    assert WANTED_TOPICS["TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"].title == "Base Low MC Freshies"
    assert WANTED_TOPICS["TELEGRAM_SNS_TOPIC_ID"].title == "SNS Tracker"
    assert WANTED_TOPICS["TELEGRAM_BUNDLES_TOPIC_ID"].title == "Bundles (SOL)"
    assert WANTED_TOPICS["TELEGRAM_STRONG_LAUNCH_TOPIC_ID"].title == "Strong launches"
    assert "TELEGRAM_VANISH_TOPIC_ID" not in WANTED_TOPICS


def test_reconcile_topic_plan_assigns_allowed_icon_colors_to_every_topic():
    allowed_colors = set(TELEGRAM_TOPIC_COLORS.values())

    assert WANTED_TOPICS
    assert all(topic.icon_color in allowed_colors for topic in WANTED_TOPICS.values())

def test_reconcile_topic_plan_creates_robinhood_topics():
    assert WANTED_TOPICS["TELEGRAM_RH_FRESHIES_TOPIC_ID"].title == "RH Freshies"
    assert WANTED_TOPICS["TELEGRAM_RH_BIG_FRESHIES_TOPIC_ID"].title == "RH Big Freshies"
    assert WANTED_TOPICS["TELEGRAM_RH_LOW_MC_FRESHIES_TOPIC_ID"].title == "RH Low MC Freshies"
    assert WANTED_TOPICS["TELEGRAM_RH_DEPLOYS_TOPIC_ID"].title == "RH Deploys"


def test_reconcile_topic_plan_creates_feedback_topic_for_v1_startup_messages():
    assert WANTED_TOPICS["TELEGRAM_FEEDBACK_TOPIC_ID"].title == "Feedback"


class _DeletedTopicTelegram:
    def __init__(self):
        self.calls = []

    def request(self, method, payload, retries=6):
        self.calls.append((method, payload))
        if method == "sendMessage" and payload["message_thread_id"] == "123":
            raise RuntimeError("Bad Request: message thread not found")
        if method == "createForumTopic":
            return {"message_thread_id": 456}
        if method == "sendMessage":
            return {"message_id": 99}
        if method == "deleteMessage":
            return True
        raise AssertionError(f"unexpected Telegram request: {method}")


def test_reconcile_replaces_a_deleted_configured_topic_id():
    from scripts import reconcile_v2_topics

    env = {"TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "123"}
    updates = {}
    created, verified = reconcile_v2_topics.ensure_topic(
        telegram=_DeletedTopicTelegram(),
        chat_id="-100",
        env=env,
        updates=updates,
        key="TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID",
        spec=WANTED_TOPICS["TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID"],
    )

    assert created is True
    assert verified is True
    assert updates == {"TELEGRAM_BASE_LOW_MC_FRESHIES_TOPIC_ID": "456"}
