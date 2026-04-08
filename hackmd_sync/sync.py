"""Core sync engine: bidirectional HackMD <-> Obsidian sync."""

import os
import time
import shutil
import logging

from . import api as api_mod
from . import frontmatter
from . import conflict as conflict_mod
from .state import SyncState

logger = logging.getLogger(__name__)


def sanitize_filename(name):
    invalid = '<>:"/\\|?*'
    for c in invalid:
        name = name.replace(c, "_")
    return name.strip().strip(".")


def get_folder_path(note):
    if note.get("folderPaths"):
        return os.path.join(
            *[sanitize_filename(f["name"]) for f in note["folderPaths"]]
        )
    return ""


class SyncResult:
    def __init__(self):
        self.pulled = 0
        self.pushed = 0
        self.created = 0
        self.skipped = 0
        self.conflicts = []
        self.errors = []

    def __str__(self):
        parts = []
        if self.pulled:
            parts.append(f"{self.pulled} pulled")
        if self.pushed:
            parts.append(f"{self.pushed} pushed")
        if self.created:
            parts.append(f"{self.created} created")
        if self.skipped:
            parts.append(f"{self.skipped} unchanged")
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} conflicts")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts) if parts else "nothing to sync"


def run_sync(config):
    """Run a full bidirectional sync cycle."""
    hackmd_config = config["hackmd"]
    sync_config = config["sync"]

    api = api_mod.HackMDAPI(
        token=hackmd_config["api_token"],
        base_url=hackmd_config["api_base"],
        delay=sync_config["api_delay"],
    )
    state = SyncState(config["_state_file"])
    sync_dir = config["_sync_dir"]
    result = SyncResult()

    os.makedirs(sync_dir, exist_ok=True)

    # Phase 1: HackMD -> Obsidian
    logger.info("Phase 1: HackMD -> Obsidian")
    _sync_pull(api, state, sync_dir, sync_config, result)

    # Phase 2: Obsidian -> HackMD
    logger.info("Phase 2: Obsidian -> HackMD")
    _sync_push(api, state, sync_dir, sync_config, result)

    state.save()
    logger.info(f"Sync complete: {result}")
    return result


def _sync_pull(api, state, sync_dir, sync_config, result):
    """Pull updated notes from HackMD to Obsidian."""
    notes = api.list_notes()
    if not notes:
        logger.warning("No notes returned from HackMD API")
        return

    tolerance = sync_config.get("mtime_tolerance", 2)
    strategy = sync_config.get("conflict_strategy", "keep_both")

    for note in notes:
        note_id = note["id"]
        last_changed = note.get("lastChangedAt", 0)
        state_entry = state.get(note_id)

        # Check if unchanged
        if state_entry and state_entry.get("lastChangedAt") == last_changed:
            result.skipped += 1
            continue

        # Check for conflict (both sides changed)
        if state_entry and "filePath" in state_entry:
            file_path = state_entry["filePath"]
            if os.path.exists(file_path):
                try:
                    local_mtime = os.path.getmtime(file_path)
                except OSError:
                    local_mtime = 0

                change_type = conflict_mod.detect(
                    note_id, state_entry, last_changed, local_mtime, tolerance
                )

                if change_type == "conflict":
                    # Fetch HackMD content for conflict resolution
                    full_note = api.get_note(note_id)
                    if not full_note:
                        result.errors.append(f"Failed to fetch: {note.get('title')}")
                        continue

                    hackmd_content = frontmatter.strip_hackmd_frontmatter(
                        full_note.get("content", "")
                    )
                    with open(file_path, "r", encoding="utf-8") as f:
                        _, local_body = frontmatter.parse(f.read())

                    resolution, msg = conflict_mod.resolve(
                        strategy, file_path, hackmd_content, local_body,
                        note.get("title", "Untitled"),
                    )
                    result.conflicts.append(msg)
                    logger.warning(msg)

                    if resolution == "obsidian":
                        result.skipped += 1
                        continue
                    elif resolution == "kept_both":
                        result.skipped += 1
                        continue
                    # hackmd wins: fall through to overwrite

                elif change_type == "obsidian_only":
                    # Local changed, HackMD didn't -> skip pull, will push in Phase 2
                    result.skipped += 1
                    continue

        # Fetch full note content
        full_note = api.get_note(note_id)
        if not full_note:
            result.errors.append(f"Failed to fetch: {note.get('title')}")
            continue

        title = note.get("title", "Untitled") or "Untitled"
        content = frontmatter.strip_hackmd_frontmatter(full_note.get("content", ""))
        folder_path = get_folder_path(note)
        safe_title = sanitize_filename(title)

        dir_path = os.path.join(sync_dir, folder_path) if folder_path else sync_dir
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, f"{safe_title}.md")

        fm = frontmatter.build(
            note_id, note.get("tags"), note.get("publishLink", "")
        )

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fm + "\n\n" + content)
        except PermissionError:
            logger.warning(f"Skipped (locked): {file_path}")
            continue

        state.set(note_id, {
            "title": title,
            "filePath": file_path,
            "folderPath": folder_path,
            "lastChangedAt": last_changed,
            "syncedAt": int(time.time() * 1000),
            "localMtime": os.path.getmtime(file_path),
        })
        result.pulled += 1
        logger.debug(f"Pulled: {folder_path}/{title}")


def _scan_duplicate_hackmd_ids(sync_dir):
    """Return hackmd_id -> [file paths] for IDs that appear in more than one file."""
    seen = {}
    for root, dirs, files in os.walk(sync_dir):
        dirs[:] = [d for d in dirs if d != ".duplicate-archive"]
        for fname in files:
            if not fname.endswith(".md") or ".hackmd-conflict-" in fname:
                continue
            file_path = os.path.join(root, fname)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except PermissionError:
                continue
            fm, _body = frontmatter.parse(content)
            hackmd_id = fm.get("hackmd_id", "")
            if hackmd_id:
                seen.setdefault(hackmd_id, []).append(file_path)
    return {hid: paths for hid, paths in seen.items() if len(paths) > 1}


def find_duplicate_notes(sync_dir, state=None):
    """Return duplicate note mappings with a canonical path and duplicate paths."""
    duplicate_ids = _scan_duplicate_hackmd_ids(sync_dir)
    duplicates = []
    for hackmd_id, paths in sorted(duplicate_ids.items()):
        canonical = None
        if state is not None:
            entry = state.get(hackmd_id)
            if entry:
                canonical = entry.get("filePath")
        if canonical not in paths:
            canonical = sorted(paths)[0]
        duplicate_paths = [p for p in sorted(paths) if p != canonical]
        duplicates.append({
            "hackmd_id": hackmd_id,
            "canonical_path": canonical,
            "duplicate_paths": duplicate_paths,
            "all_paths": sorted(paths),
        })
    return duplicates


def archive_duplicate_notes(sync_dir, state=None, archive_root=None):
    """Move non-canonical duplicate note files into an archive directory."""
    archive_root = archive_root or os.path.join(sync_dir, ".duplicate-archive")
    archived = []
    for duplicate in find_duplicate_notes(sync_dir, state):
        for path in duplicate["duplicate_paths"]:
            rel_path = os.path.relpath(path, sync_dir)
            target = os.path.join(archive_root, rel_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(path, target)
            archived.append({
                "hackmd_id": duplicate["hackmd_id"],
                "original_path": path,
                "archived_to": target,
                "canonical_path": duplicate["canonical_path"],
            })
    return archived


def _sync_push(api, state, sync_dir, sync_config, result):
    """Push new/modified notes from Obsidian to HackMD."""
    tolerance = sync_config.get("mtime_tolerance", 2)
    read_perm = sync_config.get("default_read_permission", "owner")
    write_perm = sync_config.get("default_write_permission", "owner")
    duplicate_ids = _scan_duplicate_hackmd_ids(sync_dir)

    for root, _dirs, files in os.walk(sync_dir):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            # Skip conflict files
            if ".hackmd-conflict-" in fname:
                continue

            file_path = os.path.join(root, fname)

            try:
                file_mtime = os.path.getmtime(file_path)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except PermissionError:
                logger.warning(f"Skipped (locked): {file_path}")
                continue

            fm, body = frontmatter.parse(content)
            hackmd_id = fm.get("hackmd_id", "")

            if hackmd_id:
                # Existing note: push if locally modified
                entry = state.get(hackmd_id)
                if entry:
                    duplicate_paths = duplicate_ids.get(hackmd_id, [])
                    if duplicate_paths:
                        canonical = entry.get("filePath") or sorted(duplicate_paths)[0]
                        if file_path != canonical:
                            logger.warning(
                                "Duplicate hackmd_id %s found in %d files; skipping non-canonical path: %s",
                                hackmd_id,
                                len(duplicate_paths),
                                file_path,
                            )
                            result.skipped += 1
                            continue

                    last_local = entry.get("localMtime", 0)
                    if file_mtime > last_local + tolerance:
                        resp = api.update_note(hackmd_id, body.strip())
                        if resp is not None:
                            # Refresh remote timestamp
                            updated = api.get_note(hackmd_id)
                            remote_ts = (
                                updated.get("lastChangedAt", 0) if updated else 0
                            )
                            entry["syncedAt"] = int(time.time() * 1000)
                            entry["localMtime"] = file_mtime
                            entry["lastChangedAt"] = remote_ts or entry.get(
                                "lastChangedAt", 0
                            )
                            state.set(hackmd_id, entry)
                            result.pushed += 1
                            logger.debug(f"Pushed: {fname}")
            else:
                # New note: create on HackMD
                title = fname.replace(".md", "")
                resp = api.create_note(
                    title, body.strip(), read_perm, write_perm
                )
                if resp and "id" in resp:
                    new_id = resp["id"]
                    new_fm = frontmatter.build(
                        new_id, hackmd_url=resp.get("publishLink", "")
                    )
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(new_fm + "\n\n" + body)
                    except PermissionError:
                        logger.warning(f"Skipped write (locked): {file_path}")

                    rel_folder = os.path.relpath(root, sync_dir)
                    state.set(new_id, {
                        "title": title,
                        "filePath": file_path,
                        "folderPath": rel_folder if rel_folder != "." else "",
                        "lastChangedAt": resp.get(
                            "lastChangedAt", int(time.time() * 1000)
                        ),
                        "syncedAt": int(time.time() * 1000),
                        "localMtime": os.path.getmtime(file_path),
                    })
                    result.created += 1
                    logger.debug(f"Created: {title}")
