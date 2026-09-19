from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PresencePayload:
    activity_type: str = "playing"
    name: str = ""
    details: str = ""
    state: str = ""
    large_image: str = ""
    large_text: str = ""
    small_image: str = ""
    small_text: str = ""


class DiscordBackend:
    def connect(self, application_id: str) -> None:
        raise NotImplementedError

    def publish(self, payload: PresencePayload) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
