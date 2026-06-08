"""Server-side Gmail via google-api-python-client + an OAuth refresh token.

NOT the Claude.ai Gmail MCP connector (that's unavailable server-side). The
`gmail_client()` builder is factored out so tests can mock it; the gmail.compose
scope covers both creating drafts and sending.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from backend.config import settings

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.compose"


def gmail_client() -> Any:  # pragma: no cover - thin OAuth wiring; mocked in tests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(  # type: ignore[no-untyped-call]
        None,
        refresh_token=settings.gmail_refresh_token,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=[GMAIL_SCOPE],
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_message(to: str, subject: str, body: str) -> EmailMessage:
    """Plain-text MIME message (To may be blank)."""
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def encode(msg: EmailMessage) -> str:
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_message(raw: str) -> str:
    """Send a base64url-encoded message via Gmail; returns the sent message id.
    Blocking — call via asyncio.to_thread from async code."""
    client = gmail_client()
    sent = client.users().messages().send(userId="me", body={"raw": raw}).execute()
    return str(sent["id"])
