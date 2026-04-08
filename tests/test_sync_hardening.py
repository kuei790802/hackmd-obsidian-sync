import io
import logging
import os
from pathlib import Path

import pytest

from hackmd_sync import cli, scheduler, sync
from hackmd_sync.sync import SyncResult


class DummyState:
    def __init__(self, mapping):
        self.mapping = mapping
        self.updated = {}

    def get(self, key):
        return self.mapping.get(key)

    def set(self, key, value):
        self.updated[key] = value
        self.mapping[key] = value


def write_note(path: Path, hackmd_id: str, body: str = "body"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nhackmd_id: {hackmd_id}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_setup_logging_non_tty_uses_file_handler_only(tmp_path, monkeypatch):
    log_file = tmp_path / "logs" / "sync.log"
    config = {"_log_file": str(log_file), "logging": {"level": "INFO"}}

    class FakeStdout(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(cli.sys, "stdout", FakeStdout())

    cli.setup_logging(config)

    root_handlers = logging.getLogger().handlers
    assert len(root_handlers) == 1
    assert isinstance(root_handlers[0], logging.FileHandler)


def test_cmd_run_skips_when_lock_exists(tmp_path, monkeypatch, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    lock_path = config_dir / "sync.lock"
    lock_path.write_text("123", encoding="utf-8")

    monkeypatch.setattr(cli, "load_config", lambda _path: {"_config_dir": str(config_dir)})
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)
    ran = {"value": False}
    monkeypatch.setattr(cli, "run_sync", lambda _config: ran.__setitem__("value", True))

    args = type("Args", (), {"config": "dummy.yaml"})()
    cli.cmd_run(args)

    out = capsys.readouterr().out
    assert "skipped" in out
    assert ran["value"] is False
    assert lock_path.exists()


def test_cmd_run_removes_stale_lock_and_runs(tmp_path, monkeypatch, capsys):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    lock_path = config_dir / "sync.lock"
    lock_path.write_text("123", encoding="utf-8")

    monkeypatch.setattr(cli, "load_config", lambda _path: {"_config_dir": str(config_dir)})
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)
    monkeypatch.setattr(cli.time, "time", lambda: 5000)
    monkeypatch.setattr(cli.os.path, "getmtime", lambda _path: 0)

    called = {"count": 0}
    monkeypatch.setattr(cli, "run_sync", lambda _config: called.__setitem__("count", called["count"] + 1) or "ok")

    args = type("Args", (), {"config": "dummy.yaml"})()
    cli.cmd_run(args)

    out = capsys.readouterr().out
    assert "Sync: ok" in out
    assert called["count"] == 1
    assert not lock_path.exists()


def test_install_launchd_uses_config_before_run(tmp_path, monkeypatch):
    plist_target = tmp_path / "agent.plist"
    captured = {}

    monkeypatch.setattr(scheduler.os.path, "expanduser", lambda p: str(plist_target) if p.startswith("~/Library/LaunchAgents/") else str(tmp_path / "sync.log"))
    monkeypatch.setattr(scheduler.os.path, "exists", lambda p: False)
    monkeypatch.setattr(scheduler.subprocess, "run", lambda *args, **kwargs: None)

    message = scheduler._install_launchd("python3", "/tmp/config.yaml", 900)
    plist = plist_target.read_text(encoding="utf-8")

    assert "<string>--config</string>" in plist
    assert plist.index("<string>--config</string>") < plist.index("<string>run</string>")
    assert message == "launchd service installed: every 900s"


@pytest.mark.parametrize(
    ("installer", "expected"),
    [
        (scheduler._install_systemd, "ExecStart=python3 -m hackmd_sync --config /tmp/config.yaml run"),
        (scheduler._install_cron, "python3 -m hackmd_sync --config /tmp/config.yaml run"),
    ],
)
def test_scheduler_uses_config_before_run_for_other_backends(tmp_path, monkeypatch, installer, expected):
    if installer is scheduler._install_systemd:
        unit_dir = tmp_path / "systemd"
        monkeypatch.setattr(scheduler.os.path, "expanduser", lambda _p: str(unit_dir))
        monkeypatch.setattr(scheduler.os, "makedirs", lambda *args, **kwargs: unit_dir.mkdir(parents=True, exist_ok=True))
        monkeypatch.setattr(scheduler.subprocess, "run", lambda *args, **kwargs: None)
        installer("python3", "/tmp/config.yaml", 900)
        service_path = unit_dir / f"{scheduler.LABEL}.service"
        assert expected in service_path.read_text(encoding="utf-8")
    else:
        monkeypatch.setattr(scheduler.subprocess, "check_output", lambda *args, **kwargs: "")

        class DummyProc:
            def communicate(self, data):
                self.data = data

        proc = DummyProc()
        monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *args, **kwargs: proc)
        installer("python3", "/tmp/config.yaml", 900)
        assert expected in proc.data


def test_scan_duplicate_hackmd_ids_returns_only_duplicates(tmp_path):
    write_note(tmp_path / "a.md", "dup-1")
    write_note(tmp_path / "nested" / "b.md", "dup-1")
    write_note(tmp_path / "c.md", "uniq-1")

    duplicates = sync._scan_duplicate_hackmd_ids(str(tmp_path))

    assert sorted(Path(p).name for p in duplicates["dup-1"]) == ["a.md", "b.md"]
    assert "uniq-1" not in duplicates


def test_sync_push_skips_non_canonical_duplicate(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical.md"
    duplicate = tmp_path / "nested" / "duplicate.md"
    write_note(canonical, "dup-1", body="canonical body")
    write_note(duplicate, "dup-1", body="duplicate body")

    state = DummyState({"dup-1": {"filePath": str(canonical), "localMtime": 0, "lastChangedAt": 1}})
    result = SyncResult()

    class DummyAPI:
        def __init__(self):
            self.updated = []

        def update_note(self, note_id, body):
            self.updated.append((note_id, body))
            return {"ok": True}

        def get_note(self, note_id):
            return {"lastChangedAt": 99}

    api = DummyAPI()
    monkeypatch.setattr(sync.os.path, "getmtime", lambda path: 10 if path == str(canonical) else 11)

    sync._sync_push(
        api,
        state,
        str(tmp_path),
        {"mtime_tolerance": 0, "default_read_permission": "owner", "default_write_permission": "owner"},
        result,
    )

    assert api.updated == [("dup-1", "canonical body")]
    assert result.pushed == 1
    assert result.skipped >= 1


def test_find_duplicate_notes_prefers_state_canonical_path(tmp_path):
    canonical = tmp_path / "canonical.md"
    duplicate = tmp_path / "nested" / "duplicate.md"
    write_note(canonical, "dup-1")
    write_note(duplicate, "dup-1")

    state = DummyState({"dup-1": {"filePath": str(duplicate)}})

    duplicates = sync.find_duplicate_notes(str(tmp_path), state)

    assert len(duplicates) == 1
    assert duplicates[0]["hackmd_id"] == "dup-1"
    assert duplicates[0]["canonical_path"] == str(duplicate)
    assert duplicates[0]["duplicate_paths"] == [str(canonical)]


def test_archive_duplicate_notes_moves_only_non_canonical_files(tmp_path):
    canonical = tmp_path / "canonical.md"
    duplicate = tmp_path / "nested" / "duplicate.md"
    write_note(canonical, "dup-1")
    write_note(duplicate, "dup-1")

    state = DummyState({"dup-1": {"filePath": str(canonical)}})

    archived = sync.archive_duplicate_notes(str(tmp_path), state)

    assert len(archived) == 1
    archived_path = Path(archived[0]["archived_to"])
    assert canonical.exists()
    assert not duplicate.exists()
    assert archived_path.exists()
    assert ".duplicate-archive" in str(archived_path)


def test_cmd_duplicates_dry_run_prints_report(tmp_path, monkeypatch, capsys):
    canonical = tmp_path / "canonical.md"
    duplicate = tmp_path / "nested" / "duplicate.md"
    write_note(canonical, "dup-1")
    write_note(duplicate, "dup-1")

    config = {"_sync_dir": str(tmp_path), "_state_file": str(tmp_path / "state.json")}
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "SyncState", lambda _path: DummyState({"dup-1": {"filePath": str(canonical)}}))

    args = type("Args", (), {"config": "dummy.yaml", "apply": False})()
    cli.cmd_duplicates(args)

    out = capsys.readouterr().out
    assert "Duplicate HackMD note mappings found: 1" in out
    assert "dry-run" in out.lower()
    assert str(duplicate) in out


def test_cmd_duplicates_apply_archives_duplicates(tmp_path, monkeypatch, capsys):
    canonical = tmp_path / "canonical.md"
    duplicate = tmp_path / "nested" / "duplicate.md"
    write_note(canonical, "dup-1")
    write_note(duplicate, "dup-1")

    config = {"_sync_dir": str(tmp_path), "_state_file": str(tmp_path / "state.json")}
    monkeypatch.setattr(cli, "load_config", lambda _path: config)
    monkeypatch.setattr(cli, "SyncState", lambda _path: DummyState({"dup-1": {"filePath": str(canonical)}}))

    args = type("Args", (), {"config": "dummy.yaml", "apply": True})()
    cli.cmd_duplicates(args)

    out = capsys.readouterr().out
    assert "Archived 1 duplicate file(s)" in out
    assert canonical.exists()
    assert not duplicate.exists()


def test_scan_duplicate_hackmd_ids_ignores_archive_directory(tmp_path):
    canonical = tmp_path / "canonical.md"
    archived = tmp_path / ".duplicate-archive" / "duplicate.md"
    write_note(canonical, "dup-1")
    write_note(archived, "dup-1")

    duplicates = sync._scan_duplicate_hackmd_ids(str(tmp_path))

    assert duplicates == {}
