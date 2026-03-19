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
python3 -m hackmd_sync log         # Tail the sync log
python3 -m hackmd_sync conflicts   # List unresolved conflicts
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
