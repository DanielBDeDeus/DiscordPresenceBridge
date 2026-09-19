from __future__ import annotations

from .discord.base import PresencePayload
from .models import AppConfig, Rule
from .platforms.base import PlatformBackend
from .processes import ProcessInfo, find_matching_process
from .template import TemplateContext, render


def matching_rule(config: AppConfig) -> tuple[Rule | None, ProcessInfo | None]:
    for rule in sorted(config.rules, key=lambda item: item.priority):
        if not rule.enabled:
            continue
        process = find_matching_process(rule.process_match)
        if process is not None:
            return rule, process
    return None, None


def resolve_text_payload(
    rule: Rule,
    process: ProcessInfo,
    platform: PlatformBackend,
) -> tuple[PresencePayload | None, object]:
    media = platform.media_metadata()
    if rule.only_when_media_playing and not media.playing:
        return None, media

    window = platform.active_window()
    ctx = TemplateContext(process=process, media=media, window=window)

    def image(mode: str, value: str) -> str:
        if mode == "none":
            return ""
        if mode == "media_art":
            return media.art_url
        if mode == "static":
            return render(value, ctx)
        return ""

    payload = PresencePayload(
        activity_type=rule.activity_type,
        name=render(rule.activity_name, ctx),
        details=render(rule.details_template, ctx),
        state=render(rule.state_template, ctx),
        large_image=image(rule.large_image_mode, rule.large_image_value),
        large_text=render(rule.large_text_template, ctx),
        small_image=image(rule.small_image_mode, rule.small_image_value),
        small_text=render(rule.small_text_template, ctx),
    )
    return payload, media
