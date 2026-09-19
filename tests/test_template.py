from presence_bridge.platforms.base import ActiveWindow, MediaMetadata
from presence_bridge.processes import ProcessInfo
from presence_bridge.template import TemplateContext, render


def test_template_replacement():
    ctx = TemplateContext(
        process=ProcessInfo(pid=42, name="firefox", exe="/usr/bin/firefox"),
        media=MediaMetadata(
            playing=True,
            title="Video",
            artist="Creator",
            album="",
            art_url="https://example.invalid/art.jpg",
            player="firefox.instance",
        ),
        window=ActiveWindow(title="Video - Firefox", app_id="firefox"),
    )
    assert render("{process.name}: {media.title}", ctx) == "firefox: Video"
    assert render("{process.pid}", ctx) == "42"
