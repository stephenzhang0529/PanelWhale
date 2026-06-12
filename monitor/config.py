import os
import yaml
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    api_key: str
    poll_interval_seconds: int = 300
    alert_threshold_yellow: float = 5.0
    alert_threshold_red: float = 1.0


def _search_config_files() -> list[str]:
    """Return a list of config file paths to try, in priority order."""
    return [
        os.path.expanduser("~/.config/deepseek-monitor/config.yaml"),
        "/opt/deepseek-monitor/config.yaml",
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

    return Config(
        api_key=api_key,
        poll_interval_seconds=max(30, poll_interval),  # minimum 30s
        alert_threshold_yellow=yellow,
        alert_threshold_red=red,
    )
