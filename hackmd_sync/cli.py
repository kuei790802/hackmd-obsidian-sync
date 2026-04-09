"""CLI entry point."""

import argparse
import logging
import os
import sys
import time

from . import __version__
from .config import load_config, get_config_dir
from .sync import run_sync, find_duplicate_notes, archive_duplicate_notes, find_content_duplicates
from .state import SyncState
from .scheduler import install, uninstall


def setup_logging(config):
    log_file = config.get("_log_file", "/tmp/hackmd-sync.log")
    level = config.get("logging", {}).get("level", "INFO")

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    handlers = [logging.FileHandler(log_file)]
    if sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def cmd_run(args):
    config = load_config(args.config)
    setup_logging(config)

    lock_path = os.path.join(config["_config_dir"], "sync.lock")
    lock_fd = None
    try:
        if os.path.exists(lock_path):
            age = time.time() - os.path.getmtime(lock_path)
            if age > 3600:
                os.remove(lock_path)

        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode())
    except FileExistsError:
        logging.getLogger(__name__).warning("Another sync process is already running; skipping this cycle")
        print("Sync: skipped (another sync is already running)")
        return

    try:
        result = run_sync(config)
        print(f"Sync: {result}")
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        if os.path.exists(lock_path):
            os.remove(lock_path)


def cmd_setup(args):
    try:
        import yaml
    except ImportError:
        print("Installing PyYAML...")
        os.system(f"{sys.executable} -m pip install pyyaml -q")
        import yaml

    config_dir = get_config_dir()
    config_path = os.path.join(config_dir, "config.yaml")

    print("=== HackMD-Obsidian Sync Setup ===\n")

    # Step 1: API Token
    print("[1/4] HackMD API Token")
    print("  Get yours at: https://hackmd.io/settings#api")
    token = input("  Token: ").strip()
    if not token:
        print("Token is required.")
        sys.exit(1)

    # Verify token
    from .api import HackMDAPI
    api = HackMDAPI(token)
    me = api.get_me()
    if not me:
        print("  Invalid token. Please check and try again.")
        sys.exit(1)
    print(f"  Authenticated as: {me.get('name', 'unknown')}\n")

    # Step 2: Vault path
    print("[2/4] Obsidian Vault Path")

    # Auto-detect on macOS
    detected = None
    icloud_obsidian = os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents"
    )
    if os.path.isdir(icloud_obsidian):
        vaults = [
            d for d in os.listdir(icloud_obsidian)
            if os.path.isdir(os.path.join(icloud_obsidian, d))
        ]
        if vaults:
            detected = os.path.join(icloud_obsidian, vaults[0])

    if detected:
        print(f"  Detected: {detected}")
        use = input("  Use this? [Y/n]: ").strip().lower()
        vault_path = detected if use in ("", "y", "yes") else input("  Vault path: ").strip()
    else:
        vault_path = input("  Vault path: ").strip()

    vault_path = os.path.expanduser(vault_path)
    if not os.path.isdir(vault_path):
        print(f"  Path does not exist: {vault_path}")
        sys.exit(1)
    print()

    # Step 3: Sync folder
    print("[3/4] Sync Folder Name (inside vault)")
    sync_folder = input("  Folder name [HackMD]: ").strip() or "HackMD"
    print()

    # Step 4: Conflict strategy
    print("[4/4] Conflict Strategy")
    print("  1. keep_both  (safest - saves both versions)")
    print("  2. hackmd_wins")
    print("  3. obsidian_wins")
    choice = input("  Choice [1]: ").strip() or "1"
    strategies = {"1": "keep_both", "2": "hackmd_wins", "3": "obsidian_wins"}
    strategy = strategies.get(choice, "keep_both")
    print()

    # Write config
    config = {
        "hackmd": {
            "api_token": token,
            "api_base": "https://api.hackmd.io/v1",
        },
        "obsidian": {
            "vault_path": vault_path,
            "sync_folder": sync_folder,
        },
        "sync": {
            "interval": 300,
            "conflict_strategy": strategy,
            "default_read_permission": "owner",
            "default_write_permission": "owner",
            "api_delay": 0.3,
            "mtime_tolerance": 2,
        },
        "logging": {
            "level": "INFO",
            "max_size_mb": 10,
        },
    }

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    print(f"Config saved to: {config_path}\n")

    # First sync
    do_sync = input("Run first sync now? [Y/n]: ").strip().lower()
    if do_sync in ("", "y", "yes"):
        loaded = load_config(config_path)
        setup_logging(loaded)
        result = run_sync(loaded)
        print(f"\nDone! {result}\n")

    # Install scheduler
    do_install = input("Install as background service? [Y/n]: ").strip().lower()
    if do_install in ("", "y", "yes"):
        loaded = load_config(config_path)
        msg = install(loaded)
        print(f"\n{msg}")

    print("\nSetup complete!")


def cmd_status(args):
    config = load_config(args.config)
    state = SyncState(config["_state_file"])
    data = state.all()

    print(f"Config:     {os.path.join(config['_config_dir'], 'config.yaml')}")
    print(f"Sync dir:   {config['_sync_dir']}")
    print(f"Notes:      {len(data)}")
    print(f"Strategy:   {config['sync']['conflict_strategy']}")

    if data:
        latest = max(v.get("syncedAt", 0) for v in data.values())
        if latest:
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest / 1000))
            print(f"Last sync:  {t}")


def cmd_install(args):
    config = load_config(args.config)
    msg = install(config)
    print(msg)


def cmd_uninstall(args):
    msg = uninstall()
    print(msg)


def cmd_log(args):
    config = load_config(args.config)
    log_file = config.get("_log_file", "")
    if os.path.exists(log_file):
        os.system(f"tail -f {log_file}")
    else:
        print("No log file found.")


def cmd_conflicts(args):
    config = load_config(args.config)
    sync_dir = config["_sync_dir"]
    found = []
    for root, _dirs, files in os.walk(sync_dir):
        for f in files:
            if ".hackmd-conflict-" in f:
                found.append(os.path.join(root, f))

    if found:
        print(f"Found {len(found)} conflict file(s):\n")
        for f in found:
            print(f"  {os.path.relpath(f, sync_dir)}")
        print("\nResolve by keeping the version you want and deleting the other.")
    else:
        print("No conflicts found.")


def cmd_duplicates(args):
    config = load_config(args.config)
    sync_dir = config["_sync_dir"]
    state = SyncState(config["_state_file"])
    duplicates = find_duplicate_notes(sync_dir, state)

    if not duplicates:
        print("No duplicate HackMD note mappings found.")
        return

    print(f"Duplicate HackMD note mappings found: {len(duplicates)}\n")
    for item in duplicates:
        print(f"HackMD ID: {item['hackmd_id']}")
        print(f"  Canonical: {item['canonical_path']}")
        for path in item["duplicate_paths"]:
            print(f"  Duplicate: {path}")
        print()

    if args.apply:
        archived = archive_duplicate_notes(sync_dir, state)
        print(f"Archived {len(archived)} duplicate file(s) into {os.path.join(sync_dir, '.duplicate-archive')}")
    else:
        print("Dry-run only. Re-run with `duplicates --apply` to archive non-canonical duplicate files.")


def cmd_content_duplicates(args):
    config = load_config(args.config)
    vault_path = config["obsidian"]["vault_path"]
    duplicates = find_content_duplicates(vault_path, similarity_threshold=args.threshold)

    if not duplicates:
        print("No potential content duplicates found.")
        return

    print(f"Potential content duplicates found: {len(duplicates)}\n")
    for item in duplicates:
        print(f"Title: {item['title']}")
        print(f"  Match type: {item['mode']}")
        print(f"  Similarity: {item['similarity']}")
        for path in item['paths']:
            print(f"  Path: {path}")
        print()


def main():
    parser = argparse.ArgumentParser(
        prog="hackmd-sync",
        description="Bidirectional sync between HackMD and Obsidian",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="Path to config file")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Interactive first-time setup")
    sub.add_parser("run", help="Run one sync cycle")
    sub.add_parser("status", help="Show sync status")
    sub.add_parser("install", help="Install as background service")
    sub.add_parser("uninstall", help="Remove background service")
    sub.add_parser("log", help="Tail the sync log")
    sub.add_parser("conflicts", help="List unresolved conflicts")
    duplicates_parser = sub.add_parser("duplicates", help="Scan or archive duplicate HackMD note mappings")
    duplicates_parser.add_argument("--apply", action="store_true", help="Archive non-canonical duplicate files instead of only reporting them")
    content_dup_parser = sub.add_parser("content-duplicates", help="Scan the vault for same-title notes with identical or highly similar content")
    content_dup_parser.add_argument("--threshold", type=float, default=0.95, help="Similarity threshold for near-duplicate detection (default: 0.95)")

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "run": cmd_run,
        "status": cmd_status,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "log": cmd_log,
        "conflicts": cmd_conflicts,
        "duplicates": cmd_duplicates,
        "content-duplicates": cmd_content_duplicates,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
