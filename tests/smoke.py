"""Behavioural smoke test, run inside a real Home Assistant image."""

import asyncio
import sys

sys.path.insert(0, "/tmp")

from custom_components.matrix import (
    MatrixBot,
    _html_to_plain_text,
    notify,  # noqa: F401
    services,  # noqa: F401
)
from custom_components.matrix.const import ATTR_FORMAT, FORMAT_HTML

CASES = [
    ("plain", "plain"),
    ("<b>bold</b> and <i>italic</i>", "bold and italic"),
    ("one<br>two<br/>three", "one\ntwo\nthree"),
    ("<p>first</p><p>second</p>", "first\n\nsecond"),
    ("<ul><li>a</li><li>b</li></ul>", "a\nb"),
    ("intro<ul><li>a</li><li>b</li></ul>outro", "intro\na\nb\noutro"),
    ("<h3>Title</h3><p>first</p>one<br><br>two", "Title\n\nfirst\n\none\n\ntwo"),
    ("1 &lt; 2 &amp;&amp; 3 &gt; 2", "1 < 2 && 3 > 2"),
    ('<span data-mx-color="#ff0000">red</span>', "red"),
]
for html, expected in CASES:
    assert _html_to_plain_text(html) == expected, (html, _html_to_plain_text(html))


class FakeBot:
    """Capture what _send_message hands to the room sender."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def _handle_multi_room_send(self, target_rooms, message_type, content):
        self.sent.append(
            {"rooms": target_rooms, "type": message_type, "content": content}
        )


async def main() -> None:
    room = "!room:example.com"
    html = "<b>Alarm</b><br>CO2 &gt; 1000 &amp; rising<br><i>Living room</i>"

    bot = FakeBot()
    await MatrixBot._send_message(bot, html, [room], {ATTR_FORMAT: FORMAT_HTML})
    assert bot.sent == [
        {
            "rooms": [room],
            "type": "m.room.message",
            "content": {
                "msgtype": "m.text",
                "body": "Alarm\nCO2 > 1000 & rising\nLiving room",
                "format": "org.matrix.custom.html",
                "formatted_body": html,
            },
        }
    ], bot.sent

    # Text messages are sent verbatim, even when they look like HTML.
    for data in (None, {}, {ATTR_FORMAT: "text"}):
        bot = FakeBot()
        await MatrixBot._send_message(bot, "a <b> c &amp; d", [room], data)
        assert bot.sent[0]["content"] == {
            "msgtype": "m.text",
            "body": "a <b> c &amp; d",
        }, bot.sent


asyncio.run(main())
print("smoke ok")
