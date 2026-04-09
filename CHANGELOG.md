# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Fixed
- Prevent overlapping sync runs with a lock file so schedulers cannot pile up concurrent jobs.
- Fix scheduler command ordering so background services pass `--config` before the `run` subcommand.
- Skip non-canonical files when the same `hackmd_id` appears in multiple local notes, reducing repeated PATCH storms.
- Avoid duplicate log lines in non-interactive scheduler runs by only attaching stdout logging for TTY sessions.

### Added
- New `duplicates` CLI command for dry-run reporting of duplicate `hackmd_id` mappings.
- New `duplicates --apply` mode that archives non-canonical duplicate files into `.duplicate-archive/` instead of deleting them.
- New `content-duplicates` CLI command that scans the whole Obsidian vault for same-title notes with identical or highly similar bodies, even when frontmatter differs.
- New macOS service control commands: `service-status`, `start`, and `stop`.
- New macOS menu bar controller with `menubar`, `menubar-install`, and `menubar-uninstall` commands.

### Operational guidance
- If logs warn about duplicate `hackmd_id` values, keep a single canonical note per HackMD note ID in the vault.
- If HackMD returns 429 quota errors, reduce sync frequency and confirm only one scheduler is installed.
