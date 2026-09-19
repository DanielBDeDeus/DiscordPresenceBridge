from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


@dataclass
class CropRect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CropRect":
        data = data or {}
        return cls(
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 0)),
            height=int(data.get("height", 0)),
        )

    @property
    def valid(self) -> bool:
        return self.width > 1 and self.height > 1


@dataclass
class Rule:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = "New rule"
    enabled: bool = True
    priority: int = 100
    process_match: str = ""

    activity_type: str = "playing"
    activity_name: str = "Desktop"
    details_template: str = "{process.name}"
    state_template: str = ""
    only_when_media_playing: bool = False

    large_image_mode: str = "none"
    large_image_value: str = ""
    large_text_template: str = ""
    crop: CropRect = field(default_factory=CropRect)

    small_image_mode: str = "none"
    small_image_value: str = ""
    small_text_template: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        known = set(cls.__dataclass_fields__)
        kwargs = {k: v for k, v in data.items() if k in known and k != "crop"}
        kwargs["crop"] = CropRect.from_dict(data.get("crop"))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppConfig:
    schema_version: int = 1
    discord_application_id: str = ""
    update_interval_seconds: float = 5.0
    image_update_seconds: float = 30.0
    allow_public_crop_relay: bool = False
    rules: list[Rule] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            discord_application_id=str(data.get("discord_application_id", "")),
            update_interval_seconds=float(data.get("update_interval_seconds", 5.0)),
            image_update_seconds=float(data.get("image_update_seconds", 30.0)),
            allow_public_crop_relay=bool(data.get("allow_public_crop_relay", False)),
            rules=[Rule.from_dict(x) for x in data.get("rules", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "discord_application_id": self.discord_application_id,
            "update_interval_seconds": self.update_interval_seconds,
            "image_update_seconds": self.image_update_seconds,
            "allow_public_crop_relay": self.allow_public_crop_relay,
            "rules": [r.to_dict() for r in self.rules],
        }
