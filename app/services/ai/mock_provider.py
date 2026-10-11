"""Deterministic mock AI provider for offline development and tests."""

import hashlib
import json
import re
from typing import Optional

from app.services.ai.base import AIResult, BaseAIProvider

_HOOKS: list[str] = [
    "Stop scrolling, this one is different",
    "Your new favorite just dropped",
    "This design speaks before you do",
    "Warning: compliments incoming",
    "Not just merch, it is a mood",
    "Designed to turn heads daily",
]

_EMOJIS: list[str] = ["🔥", "✨", "😍", "🚀", "💯", "🎨", "😎", "🌟"]

_GENERIC_TAGS: list[str] = [
    "#PrintOnDemand",
    "#POD",
    "#ShopSmall",
    "#SmallBusiness",
    "#GiftIdeas",
    "#NewDrop",
    "#MustHave",
    "#TrendingNow",
    "#CustomGifts",
    "#UniqueGifts",
    "#GiftForHim",
    "#GiftForHer",
    "#TeeStyle",
    "#HoodieSeason",
]


def _digest(seed: str) -> bytes:
    """Return a deterministic SHA-256 digest for the seed string."""
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _rotated(pool: list[str], seed: str, count: int) -> list[str]:
    """Return count deterministic unique items from pool via rotation."""
    if not pool or count <= 0:
        return []
    start = _digest(seed)[0] % len(pool)
    rotated = pool[start:] + pool[:start]
    return rotated[: min(count, len(rotated))]


def _title_from_prompt(prompt: str) -> str:
    """Extract the product title line from a prompt, with fallback."""
    match = re.search(r"Product title:\s*([^\n]+)", prompt)
    if match and match.group(1).strip():
        return match.group(1).strip()
    match = re.search(r"Title:\s*([^\n]+)", prompt)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return "this design"


def _field_from_prompt(prompt: str, label: str) -> Optional[str]:
    """Extract a generic 'Label: value' line from a prompt."""
    match = re.search(rf"{re.escape(label)}:\s*([^\n]+)", prompt)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return None


def _words(text: str) -> list[str]:
    """Split text into lowercase alphanumeric words."""
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def _mock_hashtags(title: str, niche: str, seed: str, count: int = 11) -> list[str]:
    """Build a deterministic hashtag list from title and niche words."""
    tags: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        core = re.sub(r"[^\w]", "", raw)
        if not core:
            return
        tag = "#" + core
        if tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)

    niche_words = [w for w in re.split(r"[^A-Za-z0-9]+", niche or "") if w]
    if niche_words:
        _add("".join(w.capitalize() for w in niche_words))
    for word in _words(title):
        if len(word) >= 4 and len(tags) < 5:
            _add(word.capitalize())
    for generic in _rotated(_GENERIC_TAGS, seed, count):
        if len(tags) >= count:
            break
        _add(generic.lstrip("#"))
    return tags[:count]


def _mock_caption(title: str, niche: str, tone: str, seed: str, price: Optional[str], store: Optional[str]) -> str:
    """Build a deterministic realistic caption mentioning the product."""
    digest = _digest(seed + tone)
    hook = _HOOKS[digest[0] % len(_HOOKS)]
    emoji_a = _EMOJIS[digest[1] % len(_EMOJIS)]
    emoji_b = _EMOJIS[digest[2] % len(_EMOJIS)]
    emoji_c = _EMOJIS[digest[3] % len(_EMOJIS)]
    niche_bit = f" from our {niche} collection" if niche else ""
    price_bit = f" Grab yours today for just {price}." if price else ""
    store_bit = f" Shop now: {store}" if store else ""
    tone_opener = {
        "funny": "Fair warning: wearing it may cause spontaneous high-fives.",
        "urgent": "Do not wait, stock for popular designs moves fast.",
        "inspirational": "Wear your ambition and chase what moves you.",
        "professional": "Premium print quality on apparel made for everyday wear.",
        "friendly": "Made to make your day a little brighter.",
    }.get(tone, "Made to make your day a little brighter.")
    return (
        f"{hook}! {emoji_a} Meet the {title}{niche_bit}. {tone_opener} "
        f"Crafted with a clean, eye-catching print that looks great in photos and even better in person, "
        f"it is the kind of piece people ask about. {emoji_b} Style it with jeans, sneakers, or your favorite jacket "
        f"for an effortless everyday look that still stands out in a crowd.{price_bit}{store_bit} "
        f"Tag someone who would absolutely rock this! {emoji_c}"
    )


_GROUP_POSTS: dict[str, dict[str, str]] = {
    "show_your_ride": {
        "caption": (
            "REAL ONES ONLY — SHOW YOUR RIDE 📸🔥\n\n"
            "Every group has trailer queens and every group has the daily-driven beasts with the battle scars to prove it. "
            "Only real drivers post the dirty one — so drop ONE pic of your machine with year + model. 👇\n\n"
            "If yours is a little dusty from actually being driven, you already earned my respect. 😎\n\n"
            "I'll go first in the comments. Who here has the hardest-working setup?"
        ),
        "call_to_action": "Real ones: drop ONE pic of your machine with year + model 👇",
        "image_idea": "Row of daily-driven muscle cars and bikes at a golden-hour meet, dust and pride visible.",
    },
    "first_bike_story": {
        "caption": (
            "Your FIRST bike made you who you are 🏍️💭\n\n"
            "Mine was a beat-up little starter that stalled at every light — and I loved it like a brother. "
            "Every scar on that tank is a lesson no video could ever teach.\n\n"
            "Brotherhood check: what was your first bike, and which ONE memory still hits you hardest? 👇"
        ),
        "call_to_action": "Tell us your first bike + the memory that still hits hardest 👇",
        "image_idea": "Nostalgic photo of a beginner rider on a small used motorcycle at sunset.",
    },
    "guess_the_muscle_car": {
        "caption": (
            "ONLY 1 IN 20 GETS THIS — GUESS THE MUSCLE 🏁🔊\n\n"
            "V8 rumble, shaker hood, and a name that terrified the neighbors back in '71. 😤\n\n"
            "Real American-muscle blood: drop your year + model guess. No googling — honor system, posers will be exposed. 👇\n\n"
            "Closest guess owns the thread until the next round. Who's got it?"
        ),
        "call_to_action": "Prove it: year + model guess, no googling 👇",
        "image_idea": "Close-up teaser: muscle-car hood scoop and headlight in dramatic shadow.",
    },
    "dream_garage": {
        "caption": (
            "JDM vs MUSCLE — YOU CAN ONLY KEEP TWO 🚗🏍️\n\n"
            "One car, one bike. The rest vanish at midnight. JDM precision or American thunder — pick your bloodline and DEFEND it. 👇\n\n"
            "No fence-sitting. Your garage says everything about who you are. Which two stay and why?"
        ),
        "call_to_action": "Pick your bloodline: 1 car + 1 bike that stay, and why 👇",
        "image_idea": "Split garage scene: JDM tuner on one side, American muscle on the other, tense face-off.",
    },
    "mod_monday": {
        "caption": (
            "MOD MONDAY — FLEX OR CONFESS 🔧\n\n"
            "Real builders know: one mod was worth every penny, one mod still keeps you up at night. 😅\n\n"
            "Drop a pic + what you paid. The brotherhood votes: certified upgrade or certified L? Let's save each other some money this week! 👇"
        ),
        "call_to_action": "Flex your best mod, confess your worst — pics welcome 👇",
        "image_idea": "Hands wrenching on a tuned engine in a home garage, tools everywhere.",
    },
    "road_trip_memory": {
        "caption": (
            "The road that changed you 🛣️🌄\n\n"
            "Every rider and driver has ONE route burned into memory — the sunrise run, the coastal blast, the mountain pass with your people. "
            "Drop your favourite shot + the route every member of this brotherhood should ride once before they hang it up. 👇\n\n"
            "I'm carving the group's bucket list from your answers."
        ),
        "call_to_action": "Drop your shot + the must-ride route below 👇",
        "image_idea": "Winding mountain road with cars and bikes cruising, scenic overlook.",
    },
    "jdm_vs_muscle": {
        "caption": (
            "SETTLE IT: JDM PRECISION vs AMERICAN THUNDER 🥊\n\n"
            "JDM owners say balance and revs. Muscle owners say there is no replacement for displacement. "
            "Both sides are in this thread right now — so pick your camp and defend it like your badge depends on it. 👇\n\n"
            "Loudest argument with the most reactions wins the week. Which bloodline are you?"
        ),
        "call_to_action": "Pick your camp — JDM or MUSCLE — and defend it 👇",
        "image_idea": "Face-off poster style: Supra-style tuner vs classic V8 muscle at night.",
    },
    "brotherhood_oath": {
        "caption": (
            "THE UNWRITTEN RULE 🤝🏍️\n\n"
            "Real riders know: you never pass a stranded biker, you always throw the wave, you never leave anyone behind. "
            "Posers will never understand — brotherhood is earned, not bought.\n\n"
            "What is the ONE unwritten rule that separates real riders from weekend actors? 👇"
        ),
        "call_to_action": "Name your ONE unwritten rule of the road 👇",
        "image_idea": "Two riders stopped roadside helping a third, brotherhood moment at dusk.",
    },
    "restoration_soul": {
        "caption": (
            "BARN FIND OR FAMILY HEIRLOOM? 🏚️✨\n\n"
            "Some say restore it to factory and honor history. Some say restomod it and give it a second soul. "
            "Both sides love these old machines more than anything new off the lot.\n\n"
            "Purists vs builders: what is sitting in YOUR garage, and which way are you taking it? 👇"
        ),
        "call_to_action": "Purist or builder — what is your project and which way? 👇",
        "image_idea": "Dusty vintage car/bike in a barn with light streaming in, restoration in progress.",
    },
    "gear_status_check": {
        "caption": (
            "HONEST CHECK — WOULD YOU WEAR THIS TO A MEET? 👀\n\n"
            "Saw a design at the last meet that only real riders/drivers even understood — subtle to outsiders, "
            "instant respect to insiders. Half the crew said it was too loud, half said it was perfect.\n\n"
            "Be honest: would you ever rock something that bold to a car meet or bike night — or is it too much? 👇"
        ),
        "call_to_action": "Too loud or just right — would YOU wear it to a meet? 👇",
        "image_idea": "Back-of-crowd shot at a car/bike meet, one standout graphic tee visible, people talking.",
    },
}

_GROUP_TAGS: dict[str, list[str]] = {
    "car": ["#CarLovers", "#MuscleCar", "#JDM", "#CarCommunity", "#ClassicCars", "#CarMeet", "#JDMvsMuscle", "#DriveTastefully"],
    "bike": ["#BikeLife", "#MotorcycleLife", "#BikerBrotherhood", "#TwoWheels", "#BikerCommunity", "#RideSafe", "#MotoLove", "#VintageRestoration"],
}


def _mock_group_post(prompt: str) -> dict:
    """Build a deterministic LINK-FREE group post for mock mode."""
    niche_match = re.search(r"Niche:\s*([^\n]+)", prompt)
    niche = (niche_match.group(1).strip().lower() if niche_match else "car")
    if niche not in ("car", "bike"):
        niche = "car"
    template_match = re.search(r"Template:\s*[^(]*\(([^)]+)\)", prompt)
    template = (template_match.group(1).strip().lower() if template_match else "show_your_ride")
    if template not in _GROUP_POSTS:
        template = "show_your_ride"
    base = _GROUP_POSTS[template]
    machine = "car" if niche == "car" else "bike"
    caption = base["caption"]
    if niche == "bike" and template == "show_your_ride":
        caption = caption.replace("drivers", "riders").replace("car meet", "bike night")
    hashtags = (_GROUP_TAGS.get(niche, _GROUP_TAGS["car"]) + ["#ShowYourRide", "#GroupFun"])[:8]
    return {
        "caption": caption,
        "hashtags": hashtags,
        "call_to_action": base["call_to_action"],
        "image_idea": base["image_idea"].replace("cars and bikes", f"{machine}s"),
    }


class MockProvider(BaseAIProvider):
    """Offline provider returning deterministic JSON without network calls."""

    def __init__(self) -> None:
        """Initialize the mock with fixed name and model."""
        self.name: str = "mock"
        self.model: str = "mock-model"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> AIResult:
        """Return a deterministic JSON payload matching the requested task."""
        prompt = f"{system_prompt}\n{user_prompt}"
        if "GROUP POST REQUEST" in prompt:
            payload = _mock_group_post(prompt)
            text = json.dumps(payload)
            return AIResult(
                text=text,
                provider=self.name,
                model=self.model,
                tokens_used=len(text.split()),
            )
        title = _title_from_prompt(prompt)
        niche = _field_from_prompt(prompt, "Niche") or ""
        tone = (_field_from_prompt(prompt, "Tone") or "friendly").strip().lower()
        price = _field_from_prompt(prompt, "Price")
        store = _field_from_prompt(prompt, "Store URL")

        if "VARIATIONS REQUEST" in prompt:
            count_match = re.search(r"Number of variations:\s*(\d+)", prompt)
            count = int(count_match.group(1)) if count_match else 3
            count = max(2, min(5, count))
            variations = [
                {
                    "caption": _mock_caption(title, niche, tone, f"{title}-{i}", price, store),
                    "hashtags": _mock_hashtags(title, niche, f"{title}-{i}", 11),
                    "call_to_action": "Tap the link and grab yours today!",
                    "image_idea": f"Lifestyle photo of the {title} in natural daylight.",
                }
                for i in range(1, count + 1)
            ]
            payload: dict = {"variations": variations}
        elif "HASHTAG REQUEST" in prompt:
            payload = {"hashtags": _mock_hashtags(title, niche, title, 12)}
        else:
            payload = {
                "caption": _mock_caption(title, niche, tone, title, price, store),
                "hashtags": _mock_hashtags(title, niche, title, 11),
                "call_to_action": "Tap the link and grab yours today!",
                "image_idea": f"Lifestyle photo of the {title} in natural daylight.",
            }
        text = json.dumps(payload)
        return AIResult(
            text=text,
            provider=self.name,
            model=self.model,
            tokens_used=len(text.split()),
        )
