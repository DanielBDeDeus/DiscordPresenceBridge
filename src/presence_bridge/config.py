from __future__ import annotations

import json
from pathlib import Path
from platformdirs import user_config_dir

from .models import AppConfig


APP_NAME = "DiscordPresenceBridge"


def config_dir() -> Path:
    path = Path(user_config_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = config_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig()
    try:
        return AppConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        broken = path.with_name("config.broken.json")
        try:
            path.replace(broken)
        except OSError:
            pass
        return AppConfig()


def save_config(config: AppConfig) -> None:
    path = config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)
