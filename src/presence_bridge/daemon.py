from __future__ import annotations

import logging
import signal
import time

from .config import cache_dir, load_config
from .discord import LocalDiscordIPC
from .engine import matching_rule, resolve_text_payload
from .platforms import get_platform_backend
from .relay import LiveAssetRelay


LOG = logging.getLogger("presence_bridge.daemon")


def run_daemon() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    platform = get_platform_backend()
    discord = LocalDiscordIPC()
    relay = LiveAssetRelay()
    stop = False
    connected_id = ""
    last_signature = None
    last_crop_at = 0.0
    crop_url = ""
    crop_rule_id = ""
    icon_cache: dict[str, str] = {}

    def request_stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    LOG.info("DiscordPresenceBridge daemon started")

    while not stop:
        config = load_config()
        interval = max(1.0, float(config.update_interval_seconds))

        try:
            if not config.discord_application_id:
                if connected_id:
                    discord.close()
                    connected_id = ""
                time.sleep(interval)
                continue

            if connected_id != config.discord_application_id:
                discord.connect(config.discord_application_id)
                connected_id = config.discord_application_id
                last_signature = None
                LOG.info("Connected to Discord local IPC")

            rule, process = matching_rule(config)
            if rule is None or process is None:
                if last_signature is not None:
                    discord.clear()
                    last_signature = None
                    LOG.info("Presence cleared: no configured process is currently running")
                time.sleep(interval)
                continue

            payload, _media = resolve_text_payload(rule, process, platform)
            if payload is None:
                if last_signature is not None:
                    discord.clear()
                    last_signature = None
                time.sleep(interval)
                continue

            if rule.large_image_mode == "app_icon" or rule.small_image_mode == "app_icon":
                if not config.allow_public_crop_relay:
                    LOG.warning(
                        "Rule '%s' requests a local application icon but public asset relay is disabled",
                        rule.label,
                    )
                    if rule.large_image_mode == "app_icon":
                        payload.large_image = ""
                    if rule.small_image_mode == "app_icon":
                        payload.small_image = ""
                else:
                    icon = platform.application_icon(process)
                    if icon:
                        key = str(icon)
                        icon_url = icon_cache.get(key)
                        if not icon_url:
                            icon_url = relay.publish_file(icon)
                            icon_cache[key] = icon_url
                        if rule.large_image_mode == "app_icon":
                            payload.large_image = icon_url
                        if rule.small_image_mode == "app_icon":
                            payload.small_image = icon_url
                    else:
                        LOG.warning("Could not resolve an application icon for '%s'", process.name)

            if rule.large_image_mode == "screen_crop":
                if not config.allow_public_crop_relay:
                    LOG.warning(
                        "Rule '%s' requests a screen crop but public crop relay is disabled",
                        rule.label,
                    )
                    payload.large_image = ""
                elif not rule.crop.valid:
                    LOG.warning("Rule '%s' has no valid crop rectangle", rule.label)
                    payload.large_image = ""
                else:
                    now = time.monotonic()
                    due = (
                        crop_rule_id != rule.id
                        or not crop_url
                        or now - last_crop_at >= max(5.0, config.image_update_seconds)
                    )
                    if due:
                        out = cache_dir() / "discord-live-crop.webp"
                        platform.capture_crop(rule.crop, out)
                        crop_url = relay.publish_file(out)
                        crop_rule_id = rule.id
                        last_crop_at = now
                        LOG.info("Updated public crop asset for rule '%s'", rule.label)
                    payload.large_image = crop_url

            signature = repr(payload)
            if signature != last_signature:
                discord.publish(payload)
                last_signature = signature
                LOG.info("Published rule '%s' for process '%s'", rule.label, process.name)

        except Exception as exc:
            LOG.warning("Presence update failed: %s", exc)
            discord.close()
            connected_id = ""
            last_signature = None

        time.sleep(interval)

    try:
        discord.clear()
    except Exception:
        pass
    discord.close()
    relay.stop()
    LOG.info("DiscordPresenceBridge daemon stopped")
    return 0
