"""Conflict detection and resolution."""

import os
import shutil
import time
import logging

logger = logging.getLogger(__name__)


def detect(note_id, state_entry, hackmd_last_changed, local_mtime, tolerance=2):
    """Check if both sides changed since last sync.

    Returns: "none", "hackmd_only", "obsidian_only", or "conflict"
    """
    if not state_entry:
        return "none"

    last_hackmd = state_entry.get("lastChangedAt", 0)
    last_local = state_entry.get("localMtime", 0)

    hackmd_changed = hackmd_last_changed > last_hackmd
    local_changed = local_mtime > last_local + tolerance

    if hackmd_changed and local_changed:
        return "conflict"
    elif hackmd_changed:
        return "hackmd_only"
    elif local_changed:
        return "obsidian_only"
    return "none"


def resolve(strategy, file_path, hackmd_content, local_content, note_title):
    """Resolve a conflict based on the configured strategy.

    Returns: ("hackmd" | "obsidian" | "kept_both", message)
    """
    if strategy == "hackmd_wins":
        return "hackmd", f"Conflict on '{note_title}': HackMD version kept"

    elif strategy == "obsidian_wins":
        return "obsidian", f"Conflict on '{note_title}': Obsidian version kept"

    elif strategy == "keep_both":
        # Save HackMD version as a conflict file
        base, ext = os.path.splitext(file_path)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        conflict_path = f"{base}.hackmd-conflict-{timestamp}{ext}"

        try:
            with open(conflict_path, "w", encoding="utf-8") as f:
                f.write(hackmd_content)
            return (
                "kept_both",
                f"Conflict on '{note_title}': both versions saved. "
                f"Review: {os.path.basename(conflict_path)}",
            )
        except OSError as e:
            logger.error(f"Failed to save conflict file: {e}")
            return "hackmd", f"Conflict on '{note_title}': fallback to HackMD version"

    return "hackmd", "Unknown strategy, defaulting to HackMD"
