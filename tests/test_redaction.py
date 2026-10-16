"""Facebook error redaction: secrets must never leak into messages."""

from app.services.facebook.exceptions import FacebookError, redact_token_text


def test_redact_replaces_configured_token():
    assert redact_token_text("boom FAKE_TOKEN_ABC123 end") == "boom *** end"


def test_redact_is_noop_without_token():
    assert redact_token_text("nothing secret here") == "nothing secret here"


def test_facebook_error_message_is_redacted():
    err = FacebookError("Graph failed with FAKE_TOKEN_ABC123 in the URL")
    assert "FAKE_TOKEN_ABC123" not in str(err)
    assert "***" in str(err)
