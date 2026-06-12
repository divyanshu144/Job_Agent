"""Review fix: startup CRITICAL signal when jwt_secret is the published default."""

from __future__ import annotations

import logging

from backend.config import Settings, settings
from backend.main import _check_jwt_secret


def test_default_jwt_secret_logs_critical(monkeypatch, caplog):
    monkeypatch.setattr(settings, "jwt_secret", Settings.model_fields["jwt_secret"].default)
    with caplog.at_level(logging.CRITICAL, logger="backend.main"):
        _check_jwt_secret()
    crits = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(crits) == 1
    assert "forgeable" in crits[0].getMessage()


def test_custom_jwt_secret_is_quiet(monkeypatch, caplog):
    monkeypatch.setattr(settings, "jwt_secret", "a-long-random-production-secret")
    with caplog.at_level(logging.CRITICAL, logger="backend.main"):
        _check_jwt_secret()
    assert not [r for r in caplog.records if r.levelno == logging.CRITICAL]
