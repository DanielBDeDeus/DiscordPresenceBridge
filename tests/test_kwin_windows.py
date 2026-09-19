from presence_bridge.platforms.kwin_windows import (
    KWinTaskbarWindow,
    _clean_app_name,
    _records_to_processes,
)


class FakeProcess:
    def __init__(self, name: str, exe: str):
        self._name = name
        self._exe = exe

    def name(self):
        return self._name

    def exe(self):
        return self._exe


def test_steam_game_window_uses_visible_window_identity():
    record = KWinTaskbarWindow(
        pid=123,
        caption="Tabletop Simulator",
        resource_class="Tabletop Simulator.x86_64",
        desktop_file_name="",
    )

    result = _records_to_processes(
        [record],
        process_lookup=lambda _pid: FakeProcess(
            "Tabletop Simulator.x86_64",
            "/home/user/.local/share/Steam/steamapps/common/Tabletop Simulator/Tabletop Simulator.x86_64",
        ),
    )

    assert len(result) == 1
    assert result[0].display == "Tabletop Simulator"
    assert result[0].name == "Tabletop Simulator.x86_64"


def test_namespaced_desktop_id_gets_a_human_label():
    assert _clean_app_name("com.discordapp.Discord") == "Discord"


def test_multiple_windows_from_same_process_are_collapsed():
    records = [
        KWinTaskbarWindow(pid=44, caption="Tab A", resource_class="google-chrome"),
        KWinTaskbarWindow(pid=44, caption="Tab B", resource_class="google-chrome"),
    ]

    result = _records_to_processes(
        records,
        process_lookup=lambda _pid: FakeProcess("chrome", "/usr/bin/google-chrome"),
    )

    assert len(result) == 1
    assert result[0].name == "chrome"
