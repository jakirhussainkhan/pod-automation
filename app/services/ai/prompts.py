"""Prompt builders for AI Facebook post generation."""

from typing import Optional

from app.config import get_settings

ALLOWED_TONES: tuple[str, ...] = ("friendly", "funny", "urgent", "inspirational", "professional")

_JSON_ONLY = (
    "Reply with ONLY a valid JSON object. "
    "No markdown fences, no commentary, no extra text."
)

_CAPTION_RULES = (
    "Caption rules:\n"
    "- 40-220 words with a strong hook in the first line.\n"
    "- Include 1-3 relevant emojis inside the caption.\n"
    "- No false claims and no mentions of competitors.\n"
    "- Include the store URL naturally only when a store URL is provided above.\n"
)

_HASHTAG_RULES = (
    "Hashtag rules:\n"
    "- 8-15 hashtags, each starting with '#'.\n"
    "- No spaces inside a hashtag and no duplicates.\n"
    "- Mix broad tags (e.g. #PrintOnDemand) with niche-specific tags.\n"
)


def normalize_tone(tone: Optional[str]) -> str:
    """Validate the tone, falling back to 'friendly' when unknown."""
    cleaned = (tone or "").strip().lower()
    if cleaned in ALLOWED_TONES:
        return cleaned
    return "friendly"


def _language_and_voice(
    language: Optional[str], brand_voice: Optional[str]
) -> tuple[str, str]:
    """Resolve language and brand voice from args or settings."""
    settings = get_settings()
    return (
        (language or "").strip() or settings.DEFAULT_POST_LANGUAGE,
        (brand_voice or "").strip() or settings.DEFAULT_BRAND_VOICE,
    )


def _product_block(product) -> str:
    """Render product details, including optional fields when available."""
    lines = [
        f"Product title: {product.title}",
        f"Niche: {product.niche}",
    ]
    if getattr(product, "description", None):
        lines.append(f"Description: {product.description}")
    if getattr(product, "price", None) is not None:
        lines.append(f"Price: ${product.price}")
    if getattr(product, "store_url", None):
        lines.append(f"Store URL: {product.store_url}")
    return "\n".join(lines)


def _system_prompt(language: str, brand_voice: str) -> str:
    """Build the shared system prompt for post copywriting."""
    return (
        "You are an expert social media copywriter for a print-on-demand store. "
        f"Write in {language} with a {brand_voice} brand voice. "
        "You write Facebook posts that drive clicks and sales. " + _JSON_ONLY
    )


def build_post_prompts(
    product,
    tone: str = "friendly",
    language: Optional[str] = None,
    brand_voice: Optional[str] = None,
) -> tuple[str, str]:
    """Build system and user prompts for a full post generation."""
    tone = normalize_tone(tone)
    lang, voice = _language_and_voice(language, brand_voice)
    system = _system_prompt(lang, voice)
    user = (
        "Task: FULL POST REQUEST\n"
        f"{_product_block(product)}\n"
        f"Tone: {tone}\n"
        f"Language: {lang}\n"
        f"Brand voice: {voice}\n"
        "Write a Facebook post for this product. "
        "Return exactly this JSON object:\n"
        '{"caption": "...", "hashtags": ["#..."], '
        '"call_to_action": "...", "image_idea": "..."}\n'
        "Where call_to_action is a short purchase nudge and image_idea "
        "describes a photo that would suit the post.\n"
        f"{_CAPTION_RULES}"
        f"{_HASHTAG_RULES}"
    )
    return system, user


def build_caption_prompts(
    product,
    tone: str = "friendly",
    current_caption: Optional[str] = None,
    language: Optional[str] = None,
    brand_voice: Optional[str] = None,
) -> tuple[str, str]:
    """Build system and user prompts for caption regeneration."""
    tone = normalize_tone(tone)
    lang, voice = _language_and_voice(language, brand_voice)
    system = _system_prompt(lang, voice)
    if product is not None:
        context = _product_block(product)
    elif (current_caption or "").strip():
        context = f"Current caption: {(current_caption or '').strip()}"
    else:
        context = "Product title: this design"
    extra = ""
    if (current_caption or "").strip() and product is not None:
        extra = f"Current caption to improve: {(current_caption or '').strip()}\n"
    user = (
        "Task: CAPTION REQUEST\n"
        f"{context}\n"
        f"{extra}"
        f"Tone: {tone}\n"
        f"Language: {lang}\n"
        f"Brand voice: {voice}\n"
        "Write a fresh caption with the requested tone. "
        "Return exactly this JSON object:\n"
        '{"caption": "...", "hashtags": ["#..."], '
        '"call_to_action": "...", "image_idea": "..."}\n'
        f"{_CAPTION_RULES}"
        f"{_HASHTAG_RULES}"
    )
    return system, user


def build_hashtag_prompts(
    product,
    language: Optional[str] = None,
    brand_voice: Optional[str] = None,
) -> tuple[str, str]:
    """Build system and user prompts for hashtag-only generation."""
    lang, voice = _language_and_voice(language, brand_voice)
    system = _system_prompt(lang, voice)
    user = (
        "Task: HASHTAG REQUEST\n"
        f"{_product_block(product)}\n"
        f"Language: {lang}\n"
        "Generate hashtags for a Facebook post about this product. "
        "Return exactly this JSON object:\n"
        '{"hashtags": ["#...", "#..."]}\n'
        f"{_HASHTAG_RULES}"
    )
    return system, user


def build_variations_prompts(
    product,
    count: int = 3,
    tone: str = "friendly",
    language: Optional[str] = None,
    brand_voice: Optional[str] = None,
) -> tuple[str, str]:
    """Build system and user prompts for multiple A/B post variations."""
    count = max(2, min(5, int(count)))
    tone = normalize_tone(tone)
    lang, voice = _language_and_voice(language, brand_voice)
    system = _system_prompt(lang, voice)
    user = (
        "Task: VARIATIONS REQUEST\n"
        f"{_product_block(product)}\n"
        f"Number of variations: {count}\n"
        f"Tone: {tone}\n"
        f"Language: {lang}\n"
        f"Brand voice: {voice}\n"
        f"Write {count} distinct Facebook post variations for A/B testing, "
        "each with a different hook and angle. "
        "Return exactly this JSON object with exactly "
        f"{count} items in the variations array:\n"
        '{"variations": [{"caption": "...", "hashtags": ["#..."], '
        '"call_to_action": "...", "image_idea": "..."}]}\n'
        f"{_CAPTION_RULES}"
        f"{_HASHTAG_RULES}"
    )
    return system, user


GROUP_NICHES: tuple[str, ...] = ("car", "bike")

GROUP_SUBCULTURES: tuple[str, ...] = (
    "jdm",
    "american_muscle",
    "biker_brotherhood",
    "vintage_restoration",
)

GROUP_TRIGGERS: tuple[str, ...] = (
    "tribal_loyalty",
    "nostalgia",
    "debate_bait",
    "in_group_validation",
    "identity_attachment",
    "controversy",
    "status_validation",
)

GROUP_TEMPLATES: dict[str, dict] = {
    "show_your_ride": {
        "label": "Show Your Ride",
        "angle": "Tribal-loyalty roll call: members prove membership by dropping ONE photo of their real daily driver/weekend toy with year + model. Dirty cars welcome — trailer queens get called out.",
        "subculture": "american_muscle",
        "triggers": ["tribal_loyalty", "in_group_validation", "identity_attachment"],
        "indirect_selling": False,
    },
    "first_bike_story": {
        "label": "First Bike Story",
        "angle": "Nostalgia + brotherhood: members relive their very first bike — what it was, what it taught them, the one memory that still stings. Welcoming tone that validates every beginner past.",
        "subculture": "biker_brotherhood",
        "triggers": ["nostalgia", "in_group_validation", "identity_attachment"],
        "indirect_selling": False,
    },
    "guess_the_muscle_car": {
        "label": "Guess the Muscle Car",
        "angle": "Debate-bait teaser: three clues (sound/hood/legend), members must guess year + model with no googling. Honor system keeps the thread honest and argumentative.",
        "subculture": "american_muscle",
        "triggers": ["debate_bait", "controversy", "in_group_validation"],
        "indirect_selling": False,
    },
    "dream_garage": {
        "label": "Dream Garage",
        "angle": "Identity-attachment controversy: keep only TWO machines (1 car + 1 bike), rest vanish. Forces JDM-vs-Muscle and cruiser-vs-sportbike tribal warfare in the comments.",
        "subculture": "jdm",
        "triggers": ["identity_attachment", "controversy", "tribal_loyalty", "debate_bait"],
        "indirect_selling": False,
    },
    "mod_monday": {
        "label": "Mod Monday",
        "angle": "Status & gear validation: members flex the ONE mod that was worth every penny and confess the one they regret. Photos + cost welcome so others learn the hard lessons free.",
        "subculture": "jdm",
        "triggers": ["status_validation", "in_group_validation", "tribal_loyalty"],
        "indirect_selling": False,
    },
    "road_trip_memory": {
        "label": "Road Trip Memory",
        "angle": "Nostalgia + brotherhood bucket list: members drop their best road-trip photo and the ONE route every rider/driver must try once. Answers become the group's shared memory wall.",
        "subculture": "biker_brotherhood",
        "triggers": ["nostalgia", "in_group_validation", "identity_attachment"],
        "indirect_selling": False,
    },
    "jdm_vs_muscle": {
        "label": "JDM vs Muscle",
        "angle": "Pure debate-bait: JDM precision vs American Muscle thunder — pick a side and defend it. No fence-sitting allowed. Designed to split the group 50/50 and explode the comment loop.",
        "subculture": "jdm",
        "triggers": ["debate_bait", "controversy", "tribal_loyalty"],
        "indirect_selling": False,
    },
    "brotherhood_oath": {
        "label": "Brotherhood Oath",
        "angle": "Biker-brotherhood loyalty test: what unwritten rule separates real riders from weekend posers? Wave-back, help-a-stranded-rider, never-leave-anyone-behind. In-group validation only.",
        "subculture": "biker_brotherhood",
        "triggers": ["tribal_loyalty", "in_group_validation", "identity_attachment"],
        "indirect_selling": False,
    },
    "restoration_soul": {
        "label": "Restoration Soul",
        "angle": "Vintage-restoration nostalgia: barn-find or inherited machine — restore to factory or restomod it your way? Purists vs builders debate. Every old-machine owner has a scar story.",
        "subculture": "vintage_restoration",
        "triggers": ["nostalgia", "debate_bait", "identity_attachment"],
        "indirect_selling": False,
    },
    "gear_status_check": {
        "label": "Gear Status Check",
        "angle": "INDIRECT-SELLING status validation: ask whether members would ever wear/rock a bold car/bike design to a meet ('too loud or just right?'). NEVER name a product, price, or link. Goal: members voluntarily reply 'where did you get this?' — that demand is harvested later via DM only.",
        "subculture": "biker_brotherhood",
        "triggers": ["status_validation", "in_group_validation", "controversy"],
        "indirect_selling": True,
    },
}


def normalize_group_subculture(subculture: Optional[str]) -> str:
    """Validate the subculture, falling back to 'auto' (template default)."""
    cleaned = (subculture or "").strip().lower()
    if cleaned in GROUP_SUBCULTURES:
        return cleaned
    return "auto"


def normalize_group_trigger(trigger: Optional[str]) -> str:
    """Validate the psychology trigger, falling back to 'auto'."""
    cleaned = (trigger or "").strip().lower()
    if cleaned in GROUP_TRIGGERS:
        return cleaned
    return "auto"


def normalize_group_niche(niche: Optional[str]) -> str:
    """Validate the group niche, falling back to 'car'."""
    cleaned = (niche or "").strip().lower()
    if cleaned in GROUP_NICHES:
        return cleaned
    return "car"


def normalize_group_template(template: Optional[str]) -> str:
    """Validate the group template key, falling back to 'show_your_ride'."""
    cleaned = (template or "").strip().lower()
    if cleaned in GROUP_TEMPLATES:
        return cleaned
    return "show_your_ride"


def build_group_post_prompts(
    niche: str = "car",
    template: str = "show_your_ride",
    language: Optional[str] = None,
    brand_voice: Optional[str] = None,
    subculture: Optional[str] = None,
    trigger: Optional[str] = None,
) -> tuple[str, str]:
    """Build psychology-driven prompts for a viral Facebook Group post.

    Framework: US/EU automotive subcultures + subconscious identity triggers
    + indirect selling + Meta reach-down shield. Direct selling is BANNED;
    every post must earn comments through identity attachment or controversy,
    and every post must be strictly LINK-FREE (links live only in the DM funnel).
    """
    niche = normalize_group_niche(niche)
    template = normalize_group_template(template)
    lang, voice = _language_and_voice(language, brand_voice)
    spec = GROUP_TEMPLATES[template]
    label = spec["label"]
    angle = spec["angle"]
    sub = normalize_group_subculture(subculture)
    if sub == "auto":
        sub = str(spec.get("subculture", "american_muscle"))
    trig = normalize_group_trigger(trigger)
    if trig == "auto":
        trig_list = list(spec.get("triggers", ["in_group_validation"]))
        trig_display = ", ".join(trig_list)
    else:
        trig_list = [trig]
        trig_display = trig
    indirect = bool(spec.get("indirect_selling", False))
    system = (
        "You are a senior consumer-psychology copywriter embedded in US/UK/EU car & biker "
        "Facebook Groups (JDM vs American Muscle, Biker Brotherhood, Vintage Restoration). "
        f"Write in {lang} with a {voice} brand voice. "
        "You engineer comment loops with subconscious curiosity & identity triggers "
        "(tribal loyalty, nostalgia, debate-baiting, in-group validation, identity attachment, "
        "controversy, status & gear validation) — never with discounts, links, or sales pitches. "
        + _JSON_ONLY
    )
    indirect_block = (
        "INDIRECT-SELLING MODE (Status & Gear Validation):\n"
        "- Frame everything as status/identity validation, e.g. 'Only real riders know why this design matters' "
        "or 'Would you ever wear this to a car meet, or is it too loud?'.\n"
        "- NEVER name a product, price, store, discount, or where to buy.\n"
        "- NEVER answer your own bait. The GOAL is that members voluntarily comment "
        "'where did you get this?' — that demand is harvested later via DM, never in the post.\n"
        if indirect else
        "NO-SELLING MODE:\n"
        "- Write about identity, memory, loyalty, or rivalry — never about merchandise.\n"
        "- If a design/gear is mentioned at all, it is only as worn identity ('the tee I wore to the meet'), "
        "never as something to buy, with no hint of where it came from.\n"
    )
    user = (
        "Task: GROUP POST REQUEST (Psychology & Safety Framework)\n"
        f"Niche: {niche}\n"
        f"Subculture lens: {sub}\n"
        f"Template: {label} ({template})\n"
        f"Angle: {angle}\n"
        f"Active triggers: {trig_display}\n"
        f"Language: {lang}\n"
        f"Brand voice: {voice}\n"
        "Write ONE viral Facebook Group post for US/UK/EU enthusiasts. "
        "Return exactly this JSON object:\n"
        '{"caption": "...", "hashtags": ["#..."], '
        '"call_to_action": "...", "image_idea": "..."}\n'
        "PSYCHOLOGY RULES:\n"
        "- Hook line 1 must trigger identity or controversy (tribe call-out, bold take, or nostalgic punch).\n"
        "- Body must force a comment loop: pick-a-side debate, loyalty test, memory share, or status vote.\n"
        "- End with EXACTLY ONE question that is trivially easy to answer in under 10 seconds.\n"
        "- 40-140 words, 1-3 emojis inside the caption, conversational US/UK garage English.\n"
        f"{indirect_block}"
        "ZERO-LINK POLICY (absolute, no exceptions):\n"
        "- No URLs, no 'www', no '.com', no 'link in bio/comments', no 'shop/buy/order now', no prices, "
        "no discount codes, no 'DM to buy', no store names.\n"
        "- The call_to_action must be a COMMENT prompt only (e.g. 'Drop your side below'), never a purchase nudge.\n"
        "REACH-DOWN SHIELD (anti-spam variation):\n"
        "- Vary sentence rhythm, openers, and closers — never reuse a fixed template sentence verbatim.\n"
        "- Use fresh synonyms each time (rotate: ride/machine/beast, photo/pic/shot, drop/share/post).\n"
        "- 5-10 community hashtags only (e.g. #JDM #MuscleCar #BikeLife #BikerBrotherhood #VintageRestoration), "
        "no brand/store tags, varied order per post.\n"
    )
    return system, user
