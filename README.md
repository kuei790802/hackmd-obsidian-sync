# HackMD-Obsidian Sync

Bidirectional sync between [HackMD](https://hackmd.io) and your local [Obsidian](https://obsidian.md) vault.

```
HackMD (web) <---> sync engine <---> Obsidian vault (local)
```

## Why?

- Edit notes in HackMD at work, read them in Obsidian at home (or on your phone via iCloud)
- Use Obsidian's powerful linking and search on your HackMD notes
- Keep a local backup of all your HackMD content
- Collaborate on HackMD, organize in Obsidian

## Features

- **Bidirectional sync**: HackMD -> Obsidian and Obsidian -> HackMD
- **Folder structure preserved**: HackMD folders map to Obsidian subfolders
- **Conflict detection**: configurable strategies (keep both, HackMD wins, Obsidian wins)
- **Background service**: runs automatically via launchd (macOS), systemd, or cron (Linux)
- **Incremental sync**: only syncs notes that changed since last run
- **Frontmatter tracking**: each note gets `hackmd_id`, `hackmd_url`, `last_synced` metadata
- **Minimal dependencies**: Python 3.7+ and PyYAML

## Quick Start

```bash
git clone https://github.com/joshkuei/hackmd-obsidian-sync.git
cd hackmd-obsidian-sync
bash setup.sh
```

The interactive setup will guide you through:

1. **HackMD API token** — get yours at [hackmd.io/settings](https://hackmd.io/settings#api)
2. **Obsidian vault path** — auto-detected on macOS
3. **Sync folder name** — default: `HackMD/` inside your vault
4. **Conflict strategy** — how to handle simultaneous edits
5. **First sync** — pulls all HackMD notes immediately
6. **Background service** — installs auto-sync (every 5 minutes)

## How It Works

### Sync Cycle

Each sync runs two phases:

**Phase 1 — Pull (HackMD -> Obsidian)**
- Fetches note list from HackMD API
- Compares `lastChangedAt` timestamps against local state
- Downloads changed notes and writes them to the sync folder
- Preserves HackMD folder hierarchy as Obsidian subfolders

**Phase 2 — Push (Obsidian -> HackMD)**
- Scans the sync folder for modified `.md` files
- Compares file `mtime` against last sync time
- Pushes changes back to HackMD via API
- New files (without `hackmd_id`) are created as new HackMD notes

### Frontmatter

Every synced note gets YAML frontmatter:

```yaml
---
hackmd_id: "abc123"
hackmd_url: "https://hackmd.io/@user/note"
last_synced: "2026-03-19 20:00:00"
---
```

This links each local file to its HackMD counterpart. Don't remove the `hackmd_id` field.

### Conflict Handling

When the same note is edited on both sides between syncs:

| Strategy | Behavior |
|----------|----------|
| `keep_both` (default) | Saves HackMD version as `filename.hackmd-conflict-{timestamp}.md` alongside local version. You resolve manually. |
| `hackmd_wins` | HackMD version overwrites local |
| `obsidian_wins` | Local version pushes to HackMD |

Check for conflicts: `python3 -m hackmd_sync conflicts`

## Commands

```bash
python3 -m hackmd_sync setup       # Interactive first-time setup
python3 -m hackmd_sync run         # Run one sync cycle
python3 -m hackmd_sync status      # Show sync status
python3 -m hackmd_sync install     # Install as background service
python3 -m hackmd_sync uninstall   # Remove background service
python3 -m hackmd_sync service-status  # Show launchd/background service state
python3 -m hackmd_sync start       # Start the background service
python3 -m hackmd_sync stop        # Stop the background service
python3 -m hackmd_sync menubar     # Launch the macOS menu bar controller
python3 -m hackmd_sync menubar-install   # Auto-launch the menu bar controller at login
python3 -m hackmd_sync menubar-uninstall # Remove the menu bar controller
python3 -m hackmd_sync log         # Tail the sync log
python3 -m hackmd_sync conflicts   # List unresolved conflicts
python3 -m hackmd_sync duplicates  # Dry-run duplicate hackmd_id report
python3 -m hackmd_sync duplicates --apply  # Archive non-canonical duplicates safely
python3 -m hackmd_sync content-duplicates  # Scan the whole vault for same-title content duplicates
```

## Configuration

Config file location: `~/.config/hackmd-sync/config.yaml`

```yaml
hackmd:
  api_token: "YOUR_TOKEN"
  api_base: "https://api.hackmd.io/v1"

obsidian:
  vault_path: "/path/to/vault"
  sync_folder: "HackMD"          # subfolder inside vault

sync:
  interval: 300                   # seconds between syncs
  conflict_strategy: "keep_both"  # keep_both | hackmd_wins | obsidian_wins
  api_delay: 0.3                  # rate limit delay between API calls
  mtime_tolerance: 2              # seconds tolerance for file modification detection
```

See [config.example.yaml](config.example.yaml) for the full reference.

## Reliability & Safety

Recent hardening added a few protections to make scheduled sync safer:

- Only one sync process runs at a time; overlapping scheduled runs are skipped.
- Background schedulers now pass `--config` correctly before the `run` subcommand.
- If the same `hackmd_id` appears in multiple local files, only the canonical file tracked in state is pushed.
- Non-interactive scheduler runs no longer duplicate every log line into the same log file.
- On macOS you can control the sync service with `service-status`, `start`, `stop`, and the optional menu bar app.

If you see repeated `429` responses from HackMD:
- verify that only one scheduler is installed
- increase the sync interval
- check for duplicate `hackmd_id` values in your vault
- run `python3 -m hackmd_sync duplicates` to inspect duplicate mappings
- run `python3 -m hackmd_sync duplicates --apply` to archive non-canonical duplicates into `.duplicate-archive/`
- run `python3 -m hackmd_sync content-duplicates` to catch same-title notes whose bodies are identical or nearly identical across folders

## FAQ

**Q: iCloud "permission denied" errors?**
A: iCloud sometimes locks files during sync. These are automatically skipped and will sync on the next cycle.

**Q: Can I sync only specific HackMD folders?**
A: Not yet — currently syncs all notes. Folder filtering is on the roadmap.

**Q: What happens if I delete a note locally?**
A: It won't be re-downloaded (the state file tracks it). To re-sync, remove the note's entry from `~/.config/hackmd-sync/state.json`.

**Q: What happens if I delete a note on HackMD?**
A: The local file stays. It won't be pushed back unless you modify it.

## Requirements

- Python 3.7+
- PyYAML (`pip3 install pyyaml`)
- HackMD account with API token

## License

MIT
