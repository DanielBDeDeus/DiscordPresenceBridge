# DiscordPresenceBridge — Codex Instructions

## Owner and repository

Owner: DanielBDeDeus

Expected Linux working copy:

```text
~/Desktop/DiscordPresenceBridge
```

Expected GitHub remote:

```text
https://github.com/DanielBDeDeus/DiscordPresenceBridge
```

This is intended to become a real distributable desktop application, not a throwaway
prototype.

## Product goal

The user must be able to:

1. Add arbitrary local applications.
2. Decide when each application's rule is active.
3. Choose exactly which text becomes Discord activity text.
4. Use process data, media metadata, and eventually window-title metadata.
5. Choose large/small artwork.
6. Use media artwork URLs directly when available.
7. Select a screen rectangle by click-drag and use that crop as dynamic artwork.
8. Preview and edit rules in a GUI.
9. Start the background daemon automatically at login.
10. Keep Linux and Windows configuration semantics compatible.

## Architecture constraints

Shared code:
- GUI
- configuration/schema
- process matching
- templating
- rule engine
- Discord payload model
- daemon orchestration

Platform-specific code:
- `src/presence_bridge/platforms/linux_backend.py`
- `src/presence_bridge/platforms/windows_backend.py`

Discord-specific transports:
- `src/presence_bridge/discord/`

Do not put Linux-only code directly into the GUI.
Do not put Windows-only code directly into the GUI.
Do not require root for normal operation.
Do not modify Bazzite's immutable `/usr`.
Prefer XDG user directories, KDE/Wayland-safe APIs, D-Bus, portals, PipeWire,
Spectacle, and `systemd --user`.

## Discord safety/correctness

Never use:
- Discord user tokens;
- self-bots;
- Gateway impersonation;
- undocumented account automation.

The current local IPC implementation is a replaceable transport, not an excuse to mix
Discord protocol logic into the GUI.

The preferred production endpoint is the official Discord Social SDK when its native
SDK archive is available. Put proprietary SDK files under the ignored
`vendor/discord_social_sdk/` directory and implement a thin wrapper under
`native/discord_social_sdk/`.

## Dynamic screenshot privacy

Screen-crop relay must remain explicit opt-in.

Never silently enable it.

The GUI must explain that enabling it makes the selected image available through a
temporary public HTTPS URL. Do not expose arbitrary filesystem files through the local
HTTP server. Serve only in-memory/generated image assets.

Keep image refresh rate bounded. Do not stream video frames to Discord.

## Linux V1

The initial implementation uses KDE Spectacle for trusted compositor screenshots.

The crop picker works on screenshot pixel coordinates rather than assuming Wayland
global-window coordinates. That makes the first version robust enough for a fixed
desktop layout.

Future Linux work should replace/augment this with XDG ScreenCast Portal + PipeWire and
restore tokens so window/monitor capture can persist cleanly across restarts.

## Windows target

Windows is required after the Linux version is validated.

Keep shared config/rules intact. Implement in the Windows backend:

- foreground HWND/title through supported Win32 APIs;
- process/executable icon extraction;
- Windows Graphics Capture for screen/window capture;
- Windows startup registration/Task Scheduler;
- packaging using a maintained approach (PyInstaller/Nuitka/MSIX after behavior is
  stable).

Do not fork the whole application into a separate Windows codebase.

## Before claiming success

Run:

```bash
python -m compileall -q src
pytest -q
presence-bridge doctor
```

For daemon changes:

```bash
systemctl --user restart discord-presence-bridge.service
journalctl --user -u discord-presence-bridge.service -n 100 --no-pager
```

For major changes, commit before modifying and update `DEVLOG.md`.

Read `CODEX_HANDOFF.md` before continuing major implementation work.
