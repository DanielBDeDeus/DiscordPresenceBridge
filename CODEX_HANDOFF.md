# CODEX HANDOFF

## Current objective

Finish and harden DiscordPresenceBridge, first on Daniel's Bazzite/KDE desktop, then
port the same application to Windows for friends.

## Current implementation

The scaffold contains:

- PySide6 GUI.
- Process picker and per-process rules.
- Persistent config.
- Process/media template substitution.
- MPRIS metadata via D-Bus on Linux.
- Linux Spectacle full-screen capture.
- GUI click-drag crop selector.
- Crop/resize/WebP encoder.
- Opt-in temporary HTTPS relay using `cloudflared`.
- Discord Unix-socket IPC backend.
- Daemon and `systemd --user` unit.
- Git/bootstrap scripts.
- Windows backend boundary.

## First validation sequence

Do this before architectural rewrites.

1. Run `presence-bridge doctor`.
2. Confirm which Discord client Daniel actually uses: Discord Flatpak, Vesktop,
   native Discord, etc.
3. Put Daniel's Discord Application ID into the GUI.
4. Add a rule for a definitely-running process such as `firefox`.
5. Save.
6. Restart the user service.
7. Inspect:
   `journalctl --user -u discord-presence-bridge.service -f`
8. Verify text presence on Daniel's Discord profile.
9. Test MPRIS with media playing.
10. Only after text works, test live crop relay.

## Known risk: new external-image semantics

Text activity through Discord's local IPC is the fastest path to an end-to-end test.
Discord's newer Social SDK supports external image URLs, but behavior of raw external
URLs through legacy local IPC must be tested against Daniel's current Discord client.

If Discord rejects raw HTTPS asset URLs through the current IPC command, do NOT invent
user-token hacks. Implement the official Social SDK bridge instead.

## Official Social SDK milestone

Implement a tiny native helper under `native/discord_social_sdk/`.

Keep its API small:

- initialize(application_id)
- set_activity(json_payload)
- clear_activity()
- run_callbacks()
- shutdown()

Communicate with Python via either a stable C ABI loaded with `ctypes` or a tiny local
helper process with newline-delimited JSON.

Do not commit proprietary SDK binaries if their license does not allow redistribution.

## Linux capture milestone after V1

Replace fixed screenshot-pixel crops with a Portal/PipeWire source when practical:

- XDG ScreenCast Portal
- persist mode / restore token
- PipeWire frames
- crop rectangle inside selected source
- screen-layout-change handling

Keep Spectacle fallback because it is very useful on KDE.

## Windows milestone

After Linux behavior is validated:

- foreground-window metadata;
- window/process icon resolver;
- Windows Graphics Capture;
- Windows autostart;
- Windows package;
- CI/release artifacts.

Do not change the user-facing rule schema solely for Windows.

## Coding style

Prefer boring, testable modules. Do not hide errors. Put actionable messages in the
GUI and daemon log. Preserve user's existing rules across schema updates.
