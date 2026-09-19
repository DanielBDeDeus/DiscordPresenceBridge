from __future__ import annotations

from dataclasses import dataclass

from .platforms.base import ActiveWindow, MediaMetadata
from .processes import ProcessInfo


@dataclass
class TemplateContext:
    process: ProcessInfo
    media: MediaMetadata
    window: ActiveWindow


TOKENS = (
    "{process.name}",
    "{process.exe}",
    "{process.pid}",
    "{media.title}",
    "{media.artist}",
    "{media.album}",
    "{media.art_url}",
    "{media.player}",
    "{window.title}",
    "{window.app_id}",
)


def render(template: str, ctx: TemplateContext) -> str:
    values = {
        "{process.name}": ctx.process.name,
        "{process.exe}": ctx.process.exe,
        "{process.pid}": str(ctx.process.pid),
        "{media.title}": ctx.media.title,
        "{media.artist}": ctx.media.artist,
        "{media.album}": ctx.media.album,
        "{media.art_url}": ctx.media.art_url,
        "{media.player}": ctx.media.player,
        "{window.title}": ctx.window.title,
        "{window.app_id}": ctx.window.app_id,
    }
    result = template
    for token, value in values.items():
        result = result.replace(token, value)
    return result.strip()
