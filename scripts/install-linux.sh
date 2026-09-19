#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT_DIR/.venv"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
SYSTEMD_DIR="$HOME/.config/systemd/user"
CODEX_DIR="$HOME/.codex"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33mWARNING: %s\033[0m\n' "$*" >&2; }

say "DiscordPresenceBridge Linux/Bazzite installer"
printf 'Project: %s\n' "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required." >&2
    exit 1
fi

if command -v brew >/dev/null 2>&1; then
    if ! command -v cloudflared >/dev/null 2>&1; then
        say "Installing cloudflared with Homebrew (used only for opt-in live crop relay)"
        brew install cloudflared || warn "cloudflared install failed; text/media URL presence still works"
    fi
    if ! command -v gh >/dev/null 2>&1; then
        say "Installing GitHub CLI with Homebrew"
        brew install gh || warn "GitHub CLI install failed; local project setup will continue"
    fi
else
    warn "Homebrew not found. Bazzite normally includes it. cloudflared/gh were not auto-installed."
fi

say "Creating Python virtual environment"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -e "$PROJECT_DIR[dev]"

say "Validating Python source"
"$VENV/bin/python" -m compileall -q "$PROJECT_DIR/src"
"$VENV/bin/pytest" -q "$PROJECT_DIR/tests"

mkdir -p "$BIN_DIR" "$APP_DIR" "$SYSTEMD_DIR" "$CODEX_DIR"

cat > "$BIN_DIR/presence-bridge" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/presence-bridge" "\$@"
EOF
chmod +x "$BIN_DIR/presence-bridge"

cat > "$BIN_DIR/codex-presence-bridge" <<EOF
#!/usr/bin/env bash
cd "$PROJECT_DIR"
exec codex "\$@"
EOF
chmod +x "$BIN_DIR/codex-presence-bridge"

cat > "$SYSTEMD_DIR/discord-presence-bridge.service" <<EOF
[Unit]
Description=Discord Presence Bridge
After=graphical-session.target

[Service]
Type=simple
ExecStart=$VENV/bin/presence-bridge daemon
Restart=on-failure
RestartSec=4
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

cat > "$APP_DIR/discord-presence-bridge.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Discord Presence Bridge
Comment=Choose what your local applications expose as Discord activity
Exec=$VENV/bin/presence-bridge gui
Icon=preferences-system
Terminal=false
Categories=Utility;Settings;
StartupNotify=true
EOF

say "Installing Codex global project pointer without overwriting existing instructions"
if [ -s "$CODEX_DIR/AGENTS.override.md" ]; then
    GLOBAL_AGENTS="$CODEX_DIR/AGENTS.override.md"
else
    GLOBAL_AGENTS="$CODEX_DIR/AGENTS.md"
fi
START_MARK='<!-- DISCORD_PRESENCE_BRIDGE_START -->'
END_MARK='<!-- DISCORD_PRESENCE_BRIDGE_END -->'

python3 - "$GLOBAL_AGENTS" "$PROJECT_DIR" <<'PY'
from pathlib import Path
import sys, re

path = Path(sys.argv[1])
project = sys.argv[2]
start = "<!-- DISCORD_PRESENCE_BRIDGE_START -->"
end = "<!-- DISCORD_PRESENCE_BRIDGE_END -->"
block = f"""{start}
## DiscordPresenceBridge
Daniel's DiscordPresenceBridge project lives at:

`{project}`

When Daniel mentions PresenceBridge, Discord activity bridging, the custom Discord
activity GUI, or continuing this project, treat that directory as the canonical working
copy. Start by reading its `AGENTS.md` and `CODEX_HANDOFF.md`. Preserve the
cross-platform architecture: Bazzite/Linux first, Windows second.
{end}
"""

old = path.read_text(encoding="utf-8") if path.exists() else ""
pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.S)
if pattern.search(old):
    new = pattern.sub(block, old)
else:
    new = old.rstrip() + ("\n\n" if old.strip() else "") + block
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(new, encoding="utf-8")
PY

systemctl --user daemon-reload
systemctl --user enable --now discord-presence-bridge.service

say "Initializing Git repository"
cd "$PROJECT_DIR"
if [ ! -d .git ]; then
    git init -b main
fi
git add .

if ! git diff --cached --quiet; then
    if ! git config user.name >/dev/null; then
        git config user.name "DanielBDeDeus"
    fi
    if ! git config user.email >/dev/null; then
        git config user.email "DanielBDeDeus@users.noreply.github.com"
    fi
    git commit -m "Initial DiscordPresenceBridge scaffold"
fi

if command -v gh >/dev/null 2>&1; then
    if ! gh auth status >/dev/null 2>&1; then
        say "GitHub needs a one-time CLI authorization before the repository can be created"
        gh auth login --hostname github.com --git-protocol https --web ||             warn "GitHub authentication was skipped/failed; local project setup will continue."
    fi

    if gh auth status >/dev/null 2>&1; then
        say "Connecting project to DanielBDeDeus/DiscordPresenceBridge"
        if gh repo view DanielBDeDeus/DiscordPresenceBridge >/dev/null 2>&1; then
            if ! git remote get-url origin >/dev/null 2>&1; then
                git remote add origin "https://github.com/DanielBDeDeus/DiscordPresenceBridge.git"
            fi
            git push -u origin main || warn "GitHub push failed; local project is intact."
        else
            gh repo create DanielBDeDeus/DiscordPresenceBridge \
                --public \
                --source "$PROJECT_DIR" \
                --remote origin \
                --push || warn "GitHub repository creation failed; local project is intact."
        fi
    else
        warn "GitHub CLI is installed but not authenticated."
        warn "Run: gh auth login"
        warn "Then from the project: gh repo create DanielBDeDeus/DiscordPresenceBridge --public --source . --remote origin --push"
    fi
fi

say "Installation complete"
echo
echo "Open the GUI:"
echo "  presence-bridge gui"
echo
echo "Run diagnostics:"
echo "  presence-bridge doctor"
echo
echo "Watch daemon logs:"
echo "  journalctl --user -u discord-presence-bridge.service -f"
echo
echo "Start Codex in this project:"
echo "  codex-presence-bridge"
