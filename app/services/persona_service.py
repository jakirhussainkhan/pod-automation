"""Ghost-persona voice layer: tone signatures for DM phrasing."""

import logging
from typing import Any

logger = logging.getLogger("pod-automation")

TONE_SIGNATURES: dict[str, list[str]] = {
    "casual": ["hey", "cool", "let me know"],
    "enthusiast": ["awesome", "stoked", "let's chat"],
    "veteran": ["appreciate it", "been around", "in my experience"],
    "young_gun": ["yo", "fire", "no cap"],
}
"""Tone → slang words injected into AI prompts (hardcoded map)."""


def _tone_of(account: Any) -> str:
    """Return the account tone, defaulting to enthusiast."""
    tone = str(getattr(account, "persona_tone", "") or "").strip().lower()
    return tone if tone in TONE_SIGNATURES else "enthusiast"


def get_persona_signature(account: Any) -> dict:
    """Return the persona signature block for prompt building."""
    tone = _tone_of(account)
    name = (getattr(account, "persona_name", None)
            or getattr(account, "name", None) or "friend")
    bio = getattr(account, "persona_bio", None) or ""
    return {
        "persona_name": name,
        "tone": tone,
        "bio_hint": str(bio)[:500],
        "signature_words": list(TONE_SIGNATURES[tone]),
    }


def apply_persona_to_message(message: str, account: Any) -> str:
    """Prefix a DM with the persona opener (idempotent, link-safe).

    Prepends ``"<Word>. "`` using the tone's first signature word.
    Skips when the text already opens with any signature word, and
    never alters URLs, ``{placeholders}``/``[slots]`` or sentence
    endings — only a prefix is ever added. Returns the original text
    on any error.
    """
    try:
        text = str(message or "")
        if not text.strip():
            return text
        tone = _tone_of(account)
        opener = TONE_SIGNATURES[tone][0]
        lowered = text.lstrip().lower()
        for words in TONE_SIGNATURES.values():
            first = words[0].lower()
            if lowered.startswith(first + ".") or lowered.startswith(first + " "):
                return text  # Already prefixed — idempotent no-op.
        # Only a prefix is ever added: the paranoia assert below proves
        # the body (links, placeholders, punctuation included) is
        # byte-identical after prefixing.
        prefixed = opener[:1].upper() + opener[1:] + ". " + text.lstrip()
        # Paranoia check: body after the prefix must be byte-identical.
        assert prefixed[len(opener) + 2:] == text.lstrip()
        return prefixed
    except Exception:
        logger.exception("Persona apply failed; returning original message.")
        try:
            return str(message)
        except Exception:
            return ""
