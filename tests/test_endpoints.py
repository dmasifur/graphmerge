from __future__ import annotations

import pytest

from mailer import CampaignConfig, messages_endpoint, send_mail_endpoint


def _config(sender_type: str, shared_mailbox: str | None) -> CampaignConfig:
    return CampaignConfig(
        client_id="cid",
        tenant_id="tid",
        sender_type=sender_type,
        shared_mailbox=shared_mailbox,
    )


def test_personal_sender_uses_me_endpoint() -> None:
    assert send_mail_endpoint(_config("personal", None)).endswith("/me/sendMail")


def test_shared_sender_uses_named_mailbox() -> None:
    url = send_mail_endpoint(_config("shared", "marketing@example.com"))
    assert url.endswith("/users/marketing@example.com/sendMail")


def test_shared_sender_without_mailbox_raises_instead_of_falling_back() -> None:
    with pytest.raises(ValueError, match="shared mailbox"):
        send_mail_endpoint(_config("shared", None))


def test_shared_sender_with_blank_mailbox_raises() -> None:
    with pytest.raises(ValueError, match="shared mailbox"):
        send_mail_endpoint(_config("shared", "   "))


def test_messages_endpoint_shared_without_mailbox_raises() -> None:
    with pytest.raises(ValueError, match="shared mailbox"):
        messages_endpoint(_config("shared", None))


def test_messages_endpoint_personal_uses_me() -> None:
    assert messages_endpoint(_config("personal", None)).endswith("/me/messages")
