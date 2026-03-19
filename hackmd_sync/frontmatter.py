"""Frontmatter parsing and building for Obsidian markdown files."""

import time

try:
    import yaml
except ImportError:
    yaml = None


def parse(content):
    """Parse frontmatter from markdown content.

    Returns (frontmatter_dict, body_text).
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    fm_text = content[3:end].strip()
    body = content[end + 3 :].lstrip("\n")

    if yaml:
        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError:
            fm = _fallback_parse(fm_text)
    else:
        fm = _fallback_parse(fm_text)

    return fm, body


def _fallback_parse(fm_text):
    """Simple key-value parser when PyYAML is unavailable."""
    fm = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            val = val.strip().strip('"').strip("'")
            fm[key.strip()] = val
    return fm


def build(hackmd_id, tags=None, hackmd_url=""):
    """Build frontmatter block for a synced note."""
    lines = ["---"]
    lines.append(f'hackmd_id: "{hackmd_id}"')
    if tags:
        tags_str = ", ".join(tags)
        lines.append(f"tags: [{tags_str}]")
    if hackmd_url:
        lines.append(f'hackmd_url: "{hackmd_url}"')
    lines.append(f'last_synced: "{time.strftime("%Y-%m-%d %H:%M:%S")}"')
    lines.append("---")
    return "\n".join(lines)


def strip_hackmd_frontmatter(content):
    """Remove existing frontmatter from HackMD content (if any)."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3 :].lstrip("\n")
    return content
