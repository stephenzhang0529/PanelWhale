import os
import yaml
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    api_key: str
    usage_token: str = ""  # web-login token for platform.deepseek.com internal APIs
    poll_interval_seconds: int = 300
    usage_poll_interval_seconds: int = 3600  # 1 hour default
    alert_threshold_yellow: float = 5.0
    alert_threshold_red: float = 1.0


def _search_config_files() -> list[str]:
    """Return a list of config file paths to try, in priority order."""
    return [
        os.path.expanduser("~/.config/panelwhale/config.yaml"),
        "/opt/panelwhale/config.yaml",
    ]


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from file, with env-var overrides.

    Priority: explicit path > DEEPSEEK_API_KEY env var > user config > system config
    """
    cfg_data: dict = {}

    # Try config files
    paths = [config_path] if config_path else _search_config_files()
    for p in paths:
        if p and os.path.isfile(p):
            with open(p, "r") as f:
                cfg_data = yaml.safe_load(f) or {}
            break

    # API key: env var overrides file
    api_key = os.environ.get("DEEPSEEK_API_KEY", "") or cfg_data.get("api_key", "")

    # Usage token: env var overrides file (optional)
    usage_token = os.environ.get("DEEPSEEK_USAGE_TOKEN", "") or cfg_data.get(
        "usage_token", ""
    )

    poll_interval = int(
        os.environ.get("DM_POLL_INTERVAL", "")
        or cfg_data.get("poll_interval_seconds", 300)
    )

    yellow = float(
        os.environ.get("DM_ALERT_YELLOW", "")
        or cfg_data.get("alert_threshold_yellow", 5.0)
    )

    red = float(
        os.environ.get("DM_ALERT_RED", "")
        or cfg_data.get("alert_threshold_red", 1.0)
    )

    usage_poll_interval = int(
        os.environ.get("DM_USAGE_POLL_INTERVAL", "")
        or cfg_data.get("usage_poll_interval_seconds", 3600)
    )

    return Config(
        api_key=api_key,
        usage_token=usage_token,
        poll_interval_seconds=max(30, poll_interval),  # minimum 30s
        usage_poll_interval_seconds=max(600, usage_poll_interval),  # minimum 10 min
        alert_threshold_yellow=yellow,
        alert_threshold_red=red,
    )


def save_config(config: Config, path: Optional[str] = None) -> str:
    """Write *config* to the user config file as YAML.

    Returns the path that was written to.
    Raises ``OSError`` on I/O failure.
    """
    target = path or os.path.expanduser("~/.config/panelwhale/config.yaml")
    os.makedirs(os.path.dirname(target), exist_ok=True)

    yaml_text = (
        f"# PanelWhale — configuration\n"
        f"# Environment variable DEEPSEEK_API_KEY overrides the file.\n"
        f"\n"
        f"api_key: {_yaml_str(config.api_key)}\n"
        f"\n"
        f"# Usage token for platform.deepseek.com internal APIs (OPTIONAL).\n"
        f"# Get it by logging into https://platform.deepseek.com and running in\n"
        f"# the browser's DevTools console:\n"
        f"#   JSON.parse(localStorage.userToken).value\n"
        f"# Environment variable: DEEPSEEK_USAGE_TOKEN\n"
        f"usage_token: {_yaml_str(config.usage_token)}\n"
        f"\n"
        f"# How often to check balance (seconds).  Minimum: 30.\n"
        f"poll_interval_seconds: {config.poll_interval_seconds}\n"
        f"\n"
        f"# How often to poll usage data (seconds).  Minimum: 600.\n"
        f"usage_poll_interval_seconds: {config.usage_poll_interval_seconds}\n"
        f"\n"
        f"# Balance thresholds for colour changes and desktop notifications.\n"
        f"#   above yellow — normal\n"
        f"#   yellow .. red — warning (🟡)\n"
        f"#   below red      — danger  (🔴)\n"
        f"alert_threshold_yellow: {config.alert_threshold_yellow}\n"
        f"alert_threshold_red: {config.alert_threshold_red}\n"
    )

    tmp = target + ".tmp"
    with open(tmp, "w") as f:
        f.write(yaml_text)
    os.replace(tmp, target)
    return target


def _yaml_str(value: str) -> str:
    """Quote a string for YAML if non-empty, otherwise return empty quotes."""
    if not value:
        return '""'
    # Use single-quote style for readability unless the value contains a single quote
    if "'" in value:
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    else:
        return f"'{value}'"
