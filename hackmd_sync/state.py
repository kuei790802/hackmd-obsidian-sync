"""Sync state management with atomic writes."""

import json
import os
import tempfile
import logging

logger = logging.getLogger(__name__)


class SyncState:
    def __init__(self, state_file):
        self.state_file = state_file
        self._data = {}
        self.load()

    def load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Corrupted state file, starting fresh: {e}")
                self._data = {}
        return self._data

    def save(self):
        """Atomic write: write to temp file then rename."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.state_file), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.state_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def get(self, note_id):
        return self._data.get(note_id)

    def set(self, note_id, info):
        self._data[note_id] = info

    def remove(self, note_id):
        self._data.pop(note_id, None)

    def all(self):
        return self._data

    def path_index(self):
        """Build reverse lookup: filePath -> noteId."""
        return {
            info["filePath"]: nid
            for nid, info in self._data.items()
            if "filePath" in info
        }
