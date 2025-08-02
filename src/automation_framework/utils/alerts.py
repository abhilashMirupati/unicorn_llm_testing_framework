"""
Alerting Utilities
------------------

This module defines helper functions to send error notifications to
external channels such as Slack and email.  Alert destinations are
configured via the `alerts` section of `config.yaml`.  If no
configuration is provided the functions silently no‑op.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Optional

try:
    from slack_sdk import WebClient  # type: ignore
    from slack_sdk.errors import SlackApiError  # type: ignore
    _slack_available = True
except Exception:
    # Provide minimal stubs if slack_sdk is not installed
    _slack_available = False
    class WebClient:  # type: ignore
        def __init__(self, *args, **kwargs) -> None:
            pass
        def chat_postMessage(self, *args, **kwargs) -> None:
            raise RuntimeError("Slack SDK is unavailable")
    class SlackApiError(Exception):
        pass

from ..config import Config
from .logger import get_logger


logger = get_logger(__name__)


def send_slack_alert(message: str, config: Config) -> None:
    """Send an alert to Slack if a webhook URL is configured and slack_sdk is available."""
    webhook_url = config.get("alerts.slack_webhook_url")
    if not webhook_url or not _slack_available:
        return
    try:
        client = WebClient(token=None)
        client.chat_postMessage(channel=webhook_url, text=message)
    except Exception as exc:
        logger.error("Failed to send Slack alert: %s", exc)


def send_email_alert(subject: str, body: str, config: Config) -> None:
    """Send an email using the SMTP configuration."""
    email_cfg = config.get("alerts.email", {}) or {}
    smtp_server = email_cfg.get("smtp_server")
    if not smtp_server:
        return
    smtp_port = int(email_cfg.get("smtp_port", 587))
    sender = email_cfg.get("sender")
    recipient = email_cfg.get("recipient")
    username = email_cfg.get("username")
    password = email_cfg.get("password")
    if not (sender and recipient and username and password):
        logger.warning("Incomplete email alert configuration")
        return
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
    except Exception as exc:
        logger.error("Failed to send email alert: %s", exc)


__all__ = ["send_slack_alert", "send_email_alert"]