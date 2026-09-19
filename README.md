# DiscordPresenceBridge

A cross-platform, GUI-driven Discord desktop activity bridge.

Repository owner: **DanielBDeDeus**

Primary implementation target: **Bazzite / KDE Plasma / Wayland**  
Secondary target: **Windows 10/11**

## What V1 already does

- GUI for creating per-application Discord-presence rules.
- Running-process picker.
- Persistent JSON configuration.
- Template variables for process and Linux MPRIS media metadata.
- Discord local IPC publishing without a user token/self-bot.
- Linux/KDE screenshot capture through Spectacle.
- Click-and-drag crop selection from a fresh desktop screenshot.
- Best-effort automatic Linux application-icon resolution for large/small artwork.
- Repeated crop capture for dynamic artwork.
- Optional localhost HTTP asset server + Cloudflare Quick Tunnel relay so a local
  screenshot can become a Discord-fetchable HTTPS image.
- Explicit opt-in for public crop relay.
- `systemd --user` autostart on Bazzite.
- Cross-platform architecture with a separate Windows backend.
- Codex handoff files.
- GitHub bootstrap targeting:
  `https://github.com/DanielBDeDeus/DiscordPresenceBridge`

## Install on Bazzite

From the extracted project:

```bash
./scripts/install-linux.sh
```

Then open **Discord Presence Bridge** from KDE, or run:

```bash
presence-bridge gui
```

Diagnostics:

```bash
presence-bridge doctor
```

Live service logs:

```bash
journalctl --user -u discord-presence-bridge.service -f
```

## Discord setup

Create a Discord Application in the Developer Portal and copy its **Application ID**.
Paste that ID into the GUI and save.

The current transport intentionally lives behind a backend interface. V1 uses the local
Discord IPC protocol to make the first Linux version testable immediately. The project
also reserves `native/discord_social_sdk/` and `vendor/discord_social_sdk/` for the
official Discord Social SDK implementation when its SDK package is supplied.

## Dynamic screenshot artwork

A local file cannot be fetched by your friends' Discord clients. The Linux V1 therefore
has an optional relay:

1. Spectacle captures your desktop.
2. You select a rectangle in the GUI.
3. The daemon periodically captures and crops that rectangle.
4. A local HTTP server serves only generated image assets.
5. `cloudflared` exposes that local server through a temporary random HTTPS URL.
6. Discord is given a changing URL for the generated image.

This is **disabled by default**. Enabling it makes the selected crop remotely reachable
through an unguessable temporary URL while the daemon is running.

## Codex

Run Codex from the repository root:

```bash
cd ~/Desktop/DiscordPresenceBridge
codex
```

The installer also creates:

```bash
codex-presence-bridge
```

The repo-root `AGENTS.md` and `CODEX_HANDOFF.md` explain the architecture and next work.
