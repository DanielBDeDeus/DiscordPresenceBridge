from presence_bridge.processes import ProcessInfo, _looks_like_visible_app, desktop_entry_aliases


def test_visible_desktop_entry_builds_process_aliases():
    entry = """
[Desktop Entry]
Type=Application
Name=Firefox
Exec=/usr/bin/firefox %u
StartupWMClass=firefox
"""
    aliases = desktop_entry_aliases(entry, "org.mozilla.firefox")
    assert "firefox" in aliases
    assert "org.mozilla.firefox" in aliases


def test_hidden_desktop_entry_is_not_user_facing():
    entry = """
[Desktop Entry]
Type=Application
NoDisplay=true
Exec=/usr/bin/background-helper
"""
    assert desktop_entry_aliases(entry, "background-helper") == set()


def test_flatpak_launcher_matches_visible_process():
    entry = """
[Desktop Entry]
Type=Application
Exec=/usr/bin/flatpak run --branch=stable com.discordapp.Discord
StartupWMClass=discord
"""
    aliases = desktop_entry_aliases(entry, "com.discordapp.Discord")
    process = ProcessInfo(pid=10, name="Discord", exe="/app/Discord")
    assert _looks_like_visible_app(process, aliases)
