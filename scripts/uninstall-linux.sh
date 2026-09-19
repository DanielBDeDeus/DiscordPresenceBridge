#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

systemctl --user disable --now discord-presence-bridge.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/discord-presence-bridge.service"
rm -f "$HOME/.local/share/applications/discord-presence-bridge.desktop"
rm -f "$HOME/.local/bin/presence-bridge"
rm -f "$HOME/.local/bin/codex-presence-bridge"
systemctl --user daemon-reload

echo "Removed installed launchers/service."
echo "Project source was NOT deleted:"
echo "  $PROJECT_DIR"
echo "User config was NOT deleted:"
echo "  ${XDG_CONFIG_HOME:-$HOME/.config}/DiscordPresenceBridge"
