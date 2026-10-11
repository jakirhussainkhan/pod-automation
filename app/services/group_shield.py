"""Reach-down shield: anti-spam text variation + zero-link enforcement.

Every group post passes through :func:`shield_group_post` after AI generation
so Meta's duplicate-text detector sees fresh phrasing each time, and so no
product link can ever leak into a main post (links live only in the DM funnel).
"""

import random
import re
from typing import Optional

_URL_RE = re.compile(r"https?://\S+|www\.\S+|\b[\w-]+\.(com|net|org|shop|store)\b", re.IGNORECASE)

_BANNED_PHRASES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"link\s+in\s+(bio|comments?)", re.IGNORECASE), "drop it in the comments"),
    (re.compile(r"\b(shop|buy|order)\s+now\b", re.IGNORECASE), "sound off below"),
    (re.compile(r"\btap\s+the\s+link\b", re.IGNORECASE), "join the thread"),
    (re.compile(r"\bclick\s+the\s+link\b", re.IGNORECASE), "join the thread"),
    (re.compile(r"\bdm\s+to\s+buy\b", re.IGNORECASE), "drop your take"),
    (re.compile(r"\bdiscount\s+code\b", re.IGNORECASE), "bragging rights"),
    (re.compile(r"\bfree\s+shipping\b", re.IGNORECASE), "real talk"),
    (re.compile(r"\bon\s+sale\b", re.IGNORECASE), "in the wild"),
    (re.compile(r"\bfor\s+sale\b", re.IGNORECASE), "in your garage"),
    (re.compile(r"\bget\s+yours\s+today\b", re.IGNORECASE), "show yours today"),
    (re.compile(r"\bgrab\s+yours\b", re.IGNORECASE), "show yours"),
)

_PRICE_RE = re.compile(r"\$\s*\d[\d.,]*")

# Bare commercial words that must never appear in a group post. Applied after
# the phrase-level replacements above, mapping to neutral comment-loop words.
_BARE_COMMERCIAL: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bshop\s+here\b", re.IGNORECASE), "sound off here"),
    (re.compile(r"\bbuy\b", re.IGNORECASE), "rate"),
    (re.compile(r"\bshop\b", re.IGNORECASE), "scene"),
    (re.compile(r"\bstore\b", re.IGNORECASE), "meet"),
    (re.compile(r"\bprice\b", re.IGNORECASE), "story"),
)

_COMMERCIAL_TAG_STEMS: tuple[str, ...] = (
    "shop", "store", "buy", "sale", "discount", "deal", "link", "price", "order", "promo",
)

# Word-level synonym pools for variation. Keys are lowercase; replacements
# preserve the original token's capitalization.
_SYNONYMS: dict[str, list[str]] = {
    "ride": ["ride", "machine", "beast", "pride and joy"],
    "car": ["car", "machine", "muscle"],
    "bike": ["bike", "machine", "two-wheeled beast"],
    "photo": ["photo", "pic", "shot", "snap"],
    "drop": ["drop", "post", "share"],
    "comments": ["comments", "thread"],
    "guess": ["guess", "call", "shout"],
    "story": ["story", "memory", "tale"],
    "awesome": ["awesome", "legendary", "proper"],
    "best": ["best", "favourite", "all-time favourite"],
    "real": ["real", "true", "proper"],
    "quick": ["quick", "honest", "straight"],
    "question": ["question", "one for you"],
    "love": ["love", "rate", "respect"],
}

_CTA_FALLBACK = "Drop your take in the comments 👇"


def _preserve_case(original: str, replacement: str) -> str:
    """Match the replacement's case to the original token."""
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def spin_text(text: str, rng: Optional[random.Random] = None) -> str:
    """Apply synonym swaps so repeated posts never read identically."""
    source = rng or random
    if not text:
        return text

    def _swap(match: re.Match) -> str:
        word = match.group(0)
        options = _SYNONYMS.get(word.lower())
        if not options or source.random() > 0.35:
            return word
        pick = source.choice(options)
        if pick.lower() == word.lower():
            return word
        return _preserve_case(word, pick)

    pattern = re.compile(
        r"\b(" + "|".join(re.escape(key) for key in _SYNONYMS) + r")\b",
        re.IGNORECASE,
    )
    return pattern.sub(_swap, text)


def spin_hashtags(tags: list[str], rng: Optional[random.Random] = None) -> list[str]:
    """Shuffle hashtag order and rotate the tail so sets differ per post."""
    source = rng or random
    if not tags:
        return tags
    pool = list(dict.fromkeys(tags))
    source.shuffle(pool)
    if len(pool) <= 5:
        return pool
    # Keep 5-8 tags with a stable core + rotated tail.
    keep = source.randint(5, min(8, len(pool)))
    return pool[:keep]


def _scrub_commercial_tags(tags: list[str]) -> list[str]:
    """Drop hashtags with commercial stems (shop/store/sale/...) — community tags only."""
    kept: list[str] = []
    for tag in tags:
        core = tag.lstrip("#").lower()
        if any(stem in core for stem in _COMMERCIAL_TAG_STEMS):
            continue
        kept.append(tag)
    return kept


def enforce_zero_link(caption: str, call_to_action: str) -> tuple[str, str]:
    """Strip URLs, prices, and sales language; return (caption, call_to_action)."""
    clean_caption = _URL_RE.sub("", caption or "")
    clean_cta = _URL_RE.sub("", call_to_action or "")
    clean_caption = _PRICE_RE.sub("", clean_caption)
    clean_cta = _PRICE_RE.sub("", clean_cta)
    for pattern, replacement in _BANNED_PHRASES:
        clean_caption = pattern.sub(replacement, clean_caption)
        clean_cta = pattern.sub(replacement, clean_cta)
    for pattern, replacement in _BARE_COMMERCIAL:
        clean_caption = pattern.sub(replacement, clean_caption)
        clean_cta = pattern.sub(replacement, clean_cta)
    clean_caption = re.sub(r"[ \t]{2,}", " ", clean_caption).strip()
    clean_caption = re.sub(r"\n{3,}", "\n\n", clean_caption)
    clean_cta = re.sub(r"\s{2,}", " ", clean_cta).strip()
    if not clean_cta or re.search(r"(buy|shop|order|price|\$)", clean_cta, re.IGNORECASE):
        clean_cta = _CTA_FALLBACK
    return clean_caption, clean_cta


def contains_link_or_sales_pitch(text: str) -> bool:
    """Return True when text violates the zero-link / no-selling policy."""
    if not text:
        return False
    if _URL_RE.search(text):
        return True
    for pattern, _ in _BANNED_PHRASES:
        if pattern.search(text):
            return True
    for pattern, _ in _BARE_COMMERCIAL:
        if pattern.search(text):
            return True
    if _PRICE_RE.search(text):
        return True
    lowered = text.lower()
    return any(
        token in lowered
        for token in ("discount code", "free shipping", "tap the link", "click the link", "dm to buy")
    )


def shield_group_post(payload: dict, rng: Optional[random.Random] = None) -> dict:
    """Spin + zero-link-shield a validated group-post payload in place."""
    source = rng or random
    caption = spin_text(payload.get("caption", ""), source)
    cta = spin_text(payload.get("call_to_action", ""), source)
    caption, cta = enforce_zero_link(caption, cta)
    hashtags = _scrub_commercial_tags(spin_hashtags(list(payload.get("hashtags", [])), source))
    payload["caption"] = caption
    payload["call_to_action"] = cta
    payload["hashtags"] = hashtags
    payload["shield"] = {
        "zero_link": not contains_link_or_sales_pitch(caption + " " + cta + " " + " ".join(hashtags)),
        "spun": True,
    }
    return payload
