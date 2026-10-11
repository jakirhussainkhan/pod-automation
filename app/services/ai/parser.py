"""Parsing and validation for AI model outputs."""

import json
import re

from app.services.ai.exceptions import AIResponseParseError

_MAX_HASHTAGS = 15


def extract_json(raw: str) -> dict:
    """Extract the first balanced JSON object from raw model output."""
    if not raw or not str(raw).strip():
        raise AIResponseParseError("Empty AI response.")
    text = str(raw).strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    if start == -1:
        raise AIResponseParseError("No JSON object found in AI response.")
    depth = 0
    in_string = False
    escaped = False
    end = -1
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index
                    break
    if end == -1:
        raise AIResponseParseError("Unbalanced JSON object in AI response.")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIResponseParseError(f"Invalid JSON in AI response: {exc}") from exc
    if not isinstance(data, dict):
        raise AIResponseParseError("Top-level JSON must be an object.")
    return data


def normalize_hashtags(items: list[str]) -> list[str]:
    """Clean hashtag list: prefix, dedupe, drop empties, cap at 15."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, str):
            continue
        core = item.strip().lstrip("#").strip()
        core = re.sub(r"[^\w]", "", core)
        if not core:
            continue
        tag = "#" + core
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(tag)
        if len(cleaned) >= _MAX_HASHTAGS:
            break
    return cleaned


def validate_post_payload(data: dict) -> dict:
    """Validate caption payload and normalize hashtags and optionals."""
    if not isinstance(data, dict):
        raise AIResponseParseError("Post payload must be a JSON object.")
    caption = data.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        raise AIResponseParseError("Post payload needs a non-empty 'caption'.")
    hashtags = normalize_hashtags(data.get("hashtags") or [])
    call_to_action = data.get("call_to_action") or ""
    image_idea = data.get("image_idea") or ""
    if not isinstance(call_to_action, str):
        call_to_action = str(call_to_action)
    if not isinstance(image_idea, str):
        image_idea = str(image_idea)
    return {
        "caption": caption.strip(),
        "hashtags": hashtags,
        "call_to_action": call_to_action.strip(),
        "image_idea": image_idea.strip(),
    }
