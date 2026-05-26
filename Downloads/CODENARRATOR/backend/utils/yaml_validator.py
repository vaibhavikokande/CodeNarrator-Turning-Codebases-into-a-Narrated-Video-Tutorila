"""
YAML validation utilities for pipeline node outputs.
Each validator strips backtick fences, parses YAML, then checks structure.
"""

import re
from typing import Any, Dict, List

import yaml


class ValidationError(Exception):
    pass


def _strip_fences(text: str) -> str:
    """Remove leading/trailing triple-backtick code fences."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _fix_unquoted_colons(text: str) -> str:
    """
    Quote string values that contain colons.
    Key pattern: indentation + word-chars-only key + colon + space + value.
    Example fix:  description: foo: bar  →  description: "foo: bar"
    """
    result = []
    for line in text.splitlines():
        # Key must be word-chars only (no spaces inside key)
        m = re.match(r'^(\s*[\w_][\w_-]*\s*:\s+)(.+)$', line)
        if m:
            prefix, value = m.group(1), m.group(2).rstrip()
            # Skip if already quoted, is structural YAML, or is a plain number
            skip = (
                value.startswith(('"', "'", '[', '{', '-', '|', '>'))
                or value == 'null'
                or re.match(r'^-?\d+(\.\d+)?$', value)
            )
            if not skip and ':' in value:
                value = value.replace('\\', '\\\\').replace('"', '\\"')
                line = f'{prefix}"{value}"'
        result.append(line)
    return '\n'.join(result)


def _parse(text: str) -> Any:
    cleaned = _strip_fences(text)
    try:
        return yaml.safe_load(cleaned)
    except yaml.YAMLError:
        # Attempt to fix unquoted colons in string values
        fixed = _fix_unquoted_colons(cleaned)
        try:
            return yaml.safe_load(fixed)
        except yaml.YAMLError as exc2:
            raise ValidationError(f"YAML parse error: {exc2}") from exc2


def validate_abstractions(yaml_str: str) -> Dict:
    data = _parse(yaml_str)
    if not isinstance(data, dict):
        raise ValidationError("Expected a YAML mapping at top level")
    if "abstractions" not in data:
        raise ValidationError("Missing required key: abstractions")
    abstractions = data["abstractions"]
    if not isinstance(abstractions, list):
        raise ValidationError("abstractions must be a list")
    if not (5 <= len(abstractions) <= 10):
        raise ValidationError(
            f"Expected 5–10 abstractions, got {len(abstractions)}"
        )
    for i, item in enumerate(abstractions):
        if not isinstance(item, dict):
            raise ValidationError(f"Abstraction {i} must be a mapping")
        for key in ("name", "description", "file_indices"):
            if key not in item:
                raise ValidationError(f"Abstraction {i} missing key: {key}")
        if not isinstance(item["file_indices"], list):
            raise ValidationError(f"Abstraction {i} file_indices must be a list")
        for idx in item["file_indices"]:
            if not isinstance(idx, int):
                raise ValidationError(
                    f"Abstraction {i} file_indices contains non-integer: {idx!r}"
                )
    return data


def validate_relationships(yaml_str: str) -> Dict:
    data = _parse(yaml_str)
    if not isinstance(data, dict):
        raise ValidationError("Expected a YAML mapping at top level")
    for key in ("summary", "relationships"):
        if key not in data:
            raise ValidationError(f"Missing required key: {key}")
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        raise ValidationError("summary must be a non-empty string")
    rels = data["relationships"]
    if not isinstance(rels, list):
        raise ValidationError("relationships must be a list")
    for i, rel in enumerate(rels):
        if not isinstance(rel, dict):
            raise ValidationError(f"Relationship {i} must be a mapping")
        for key in ("from_abstraction", "to_abstraction", "label"):
            if key not in rel:
                raise ValidationError(f"Relationship {i} missing key: {key}")
    return data


def validate_chapter_order(yaml_str: str, abstraction_names: List[str]) -> Dict:
    data = _parse(yaml_str)
    if not isinstance(data, dict):
        raise ValidationError("Expected a YAML mapping at top level")
    if "order" not in data:
        raise ValidationError("Missing required key: order")
    order = data["order"]
    if not isinstance(order, list):
        raise ValidationError("order must be a list")
    name_set = set(abstraction_names)
    seen = set()
    for name in order:
        if name in seen:
            raise ValidationError(f"Duplicate abstraction in order: {name!r}")
        seen.add(name)
    missing = name_set - seen
    if missing:
        raise ValidationError(
            f"Abstractions missing from order: {missing}"
        )
    return data


def validate_video_script(yaml_str: str) -> Dict:
    data = _parse(yaml_str)
    if not isinstance(data, dict):
        raise ValidationError("Expected a YAML mapping at top level")
    if "segments" not in data:
        raise ValidationError("Missing required key: segments")
    segments = data["segments"]
    if not isinstance(segments, list):
        raise ValidationError("segments must be a list")
    if not (5 <= len(segments) <= 40):
        raise ValidationError(
            f"Expected 5–40 segments, got {len(segments)}"
        )
    valid_types = {
        "slide", "code", "diagram", "title",
        "definition", "statement", "bullets",
        "chapter_intro", "architecture", "summary",
    }
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValidationError(f"Segment {i} must be a mapping")
        for key in ("type", "display_content", "narration"):
            if key not in seg:
                raise ValidationError(f"Segment {i} missing key: {key}")
        if seg["type"] not in valid_types:
            raise ValidationError(
                f"Segment {i} type must be one of {valid_types}, got {seg['type']!r}"
            )
        # Warn but don't fail on empty narration — audio node handles it gracefully
        narration = str(seg.get("narration", "")).strip()
        if len(narration) < 5:
            import logging
            logging.getLogger(__name__).warning(
                "Segment %d (%s) has very short narration: %r", i, seg["type"], narration
            )
    return data
