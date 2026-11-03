from src import notifications


def test_failure_notification_without_channels_is_noop(monkeypatch):
    monkeypatch.setattr(notifications, "DISCORD_WEBHOOK_URL", "")
    monkeypatch.setattr(notifications, "ALERT_EMAIL_TO", "")
    assert notifications.notify_failure("subject", "message") == []
