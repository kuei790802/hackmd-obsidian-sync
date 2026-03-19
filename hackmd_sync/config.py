"""Configuration loading and validation."""

import os
import sys

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install it with: pip3 install pyyaml")
    sys.exit(1)

DEFAULT_CONFIG_PATHS = [
    os.path.expanduser("~/.config/hackmd-sync/config.yaml"),
    os.path.expanduser("~/.hackmd-sync/config.yaml"),
]

DEFAULTS = {
    "hackmd": {
        "api_base": "https://api.hackmd.io/v1",
    },
    "obsidian": {
        "sync_folder": "HackMD",
    },
    "sync": {
        "interval": 300,
        "conflict_strategy": "keep_both",
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


def deep_merge(base, override):
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def find_config(config_path=None):
    if config_path:
        path = os.path.expanduser(config_path)
        if os.path.exists(path):
            return path
        print(f"Config file not found: {path}")
        sys.exit(1)

    for path in DEFAULT_CONFIG_PATHS:
        if os.path.exists(path):
            return path

    return None


def load_config(config_path=None):
    path = find_config(config_path)
    if not path:
        print("No config file found. Run 'hackmd-sync setup' first.")
        sys.exit(1)

    with open(path, "r") as f:
        user_config = yaml.safe_load(f) or {}

    config = deep_merge(DEFAULTS, user_config)

    # Expand paths
    config["obsidian"]["vault_path"] = os.path.expanduser(
        config["obsidian"].get("vault_path", "")
    )

    # Derive paths
    config["_config_dir"] = os.path.dirname(path)
    config["_state_file"] = os.path.join(os.path.dirname(path), "state.json")
    config["_log_file"] = os.path.join(os.path.dirname(path), "sync.log")
    config["_sync_dir"] = os.path.join(
        config["obsidian"]["vault_path"], config["obsidian"]["sync_folder"]
    )

    validate(config)
    return config


def validate(config):
    token = config.get("hackmd", {}).get("api_token", "")
    if not token or token == "YOUR_HACKMD_API_TOKEN":
        print("Error: HackMD API token not configured.")
        sys.exit(1)

    vault = config.get("obsidian", {}).get("vault_path", "")
    if not vault or not os.path.isdir(vault):
        print(f"Error: Obsidian vault path does not exist: {vault}")
        sys.exit(1)

    strategy = config.get("sync", {}).get("conflict_strategy", "")
    if strategy not in ("keep_both", "hackmd_wins", "obsidian_wins"):
        print(f"Error: Invalid conflict_strategy: {strategy}")
        sys.exit(1)


def get_config_dir():
    """Return the preferred config directory, creating it if needed."""
    config_dir = os.path.expanduser("~/.config/hackmd-sync")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir
