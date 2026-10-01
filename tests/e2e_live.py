"""End-to-end encryption test against a real homeserver.

Runs the integration inside a real Home Assistant image against a throwaway
homeserver, with a second Matrix client playing the human in the room.
See tests/README.md for how to run it.

MODE=full (default) expects the encryption dependencies to be installed.
MODE=missing expects them to be absent and checks that nothing is sent in the
clear to an encrypted room.
"""

import asyncio
import json
import logging
import os
import sys
import uuid

sys.path.insert(0, "/tmp")

from nio import Api, AsyncClient, AsyncClientConfig, JoinResponse, RoomCreateResponse
from nio.crypto import ENCRYPTION_ENABLED
from nio.event_builders import EnableEncryptionBuilder
from nio.events.room_events import (
    Event,
    MegolmEvent,
    RoomEncryptedImage,
    RoomMessageImage,
    RoomMessageText,
)
from PIL import Image

from custom_components.matrix import (
    CONFIG_SCHEMA,
    DOMAIN,
    EVENT_MATRIX_COMMAND,
    async_setup,
)
from homeassistant import block_async_io
from homeassistant.core import HomeAssistant

MODE = os.environ.get("MODE", "full")
HOMESERVER = os.environ.get("HOMESERVER", "http://mxhs:6167")
SERVER_NAME = os.environ.get("SERVER_NAME", "mxhs")
RUN = uuid.uuid4().hex[:8]
BOT = f"@bot{RUN}:{SERVER_NAME}"
HUMAN = f"@human{RUN}:{SERVER_NAME}"
PASSWORD = "correct horse battery staple"
CONFIG_DIR = f"/tmp/cfg{RUN}"
IMAGE = "/tmp/media/snapshot.jpg"
HTML = "<b>Alarm</b><br>CO2 &gt; 1000 &amp; rising"
PLAIN = "Alarm\nCO2 > 1000 & rising"


async def _join_with_body(self, room_id: str):
    """Join a room, sending the empty JSON object the spec asks for.

    nio sends no request body at all. Synapse accepts that; the Conduit test
    homeserver rejects it with M_BAD_JSON.
    """
    method, path = Api.join(self.access_token, room_id)
    return await self._send(JoinResponse, method, path, "{}")


AsyncClient.join = _join_with_body

records: list[logging.LogRecord] = []


class _Collector(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        records.append(record)


logging.basicConfig(level=logging.WARNING)
logging.getLogger().addHandler(_Collector())


def logged(text: str) -> bool:
    return any(text in record.getMessage() for record in records)


async def register(user: str) -> None:
    client = AsyncClient(HOMESERVER)
    response = await client.register(user.split(":")[0][1:], PASSWORD)
    assert hasattr(response, "access_token"), response
    await client.logout()
    await client.close()


async def setup_hass(rooms: list[str]) -> HomeAssistant:
    """Create a Home Assistant core with the integration set up, not started."""
    hass = HomeAssistant(CONFIG_DIR)
    hass.config.allowlist_external_dirs = {"/tmp/media"}
    config = CONFIG_SCHEMA(
        {
            DOMAIN: {
                "homeserver": HOMESERVER,
                "username": BOT,
                "password": PASSWORD,
                "rooms": rooms,
                "commands": [{"word": "ping", "name": "ping"}],
            }
        }
    )
    assert await async_setup(hass, config)
    return hass


async def start_hass(rooms: list[str]) -> HomeAssistant:
    hass = await setup_hass(rooms)
    await hass.async_start()
    await hass.async_block_till_done()
    return hass


async def send(hass: HomeAssistant, room: str, message: str, data: dict) -> None:
    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {"message": message, "target": [room], "data": data},
        blocking=True,
    )


async def collect(human: AsyncClient, room: str, count: int, rounds: int = 20) -> list:
    """Sync the human's client until it has seen count new events in the room."""
    seen: list = []

    async def on_event(matrix_room, event) -> None:
        if matrix_room.room_id == room and event.sender == BOT:
            seen.append(event)

    human.add_event_callback(on_event, Event)
    for _ in range(rounds):
        await human.sync(timeout=1000)
        if len(seen) >= count:
            break
    human.event_callbacks.clear()
    return [
        e
        for e in seen
        if isinstance(
            e, (RoomMessageText, RoomMessageImage, RoomEncryptedImage, MegolmEvent)
        )
    ]


async def bot_devices() -> list[str]:
    """Return the bot's device IDs as the homeserver lists them."""
    with open(f"{CONFIG_DIR}/.matrix.conf") as conf:
        token = json.load(conf)[BOT]
    client = AsyncClient(HOMESERVER, BOT)
    client.access_token = token
    response = await client.devices()
    await client.close()
    return sorted(device.id for device in response.devices)


async def main() -> None:
    assert (MODE == "full") == ENCRYPTION_ENABLED, (MODE, ENCRYPTION_ENABLED)
    os.makedirs(CONFIG_DIR)
    os.makedirs("/tmp/media", exist_ok=True)
    Image.new("RGB", (64, 48), (200, 30, 30)).save(IMAGE)
    with open(IMAGE, "rb") as image_file:
        image_bytes = image_file.read()

    await register(BOT)
    await register(HUMAN)

    # The upgrade path on a running system: the stored token belongs to a
    # device that was created without encryption and has no keys.
    legacy = AsyncClient(HOMESERVER, BOT)
    login = await legacy.login(PASSWORD)
    legacy_device = login.device_id
    with open(f"{CONFIG_DIR}/.matrix.conf", "w") as conf:
        json.dump({BOT: login.access_token}, conf)
    await legacy.close()

    os.makedirs(f"{CONFIG_DIR}-human")
    human = AsyncClient(
        HOMESERVER,
        HUMAN,
        store_path=f"{CONFIG_DIR}-human",
        config=AsyncClientConfig(encryption_enabled=ENCRYPTION_ENABLED),
    )
    await human.login(PASSWORD)
    if ENCRYPTION_ENABLED:
        await human.keys_upload()
    created = await human.room_create(
        invite=[BOT], initial_state=[EnableEncryptionBuilder().as_dict()]
    )
    assert isinstance(created, RoomCreateResponse), created
    encrypted_room = created.room_id
    created = await human.room_create(invite=[BOT])
    plain_room = created.room_id
    await human.sync(timeout=1000, full_state=True)

    block_async_io.enable()

    if MODE == "missing":
        # Without the encryption dependencies nothing may reach the encrypted
        # room, and the unencrypted room keeps working.
        hass = await start_hass([encrypted_room, plain_room])
        assert hass.data[DOMAIN]._client.olm is None
        assert logged("The encryption dependencies are not installed")
        await send(hass, encrypted_room, HTML, {"format": "html", "images": [IMAGE]})
        assert await collect(human, encrypted_room, 1, rounds=5) == []
        assert logged("the room is encrypted and encryption is unavailable")
        await send(hass, plain_room, HTML, {"format": "html", "images": [IMAGE]})
        assert len(await collect(human, plain_room, 2)) == 2
        await hass.async_stop(force=True)
        await human.close()
        print("ok  without encryption dependencies: encrypted room refused")
        print("e2e ok (missing dependencies)")
        return

    from nio.crypto.attachments import decrypt_attachment

    # --- First start: the keyless device is replaced, then text and image
    # --- are sent encrypted. The message is queued before startup finishes.
    hass = await setup_hass([encrypted_room, plain_room])
    early = hass.async_create_task(
        send(hass, encrypted_room, HTML, {"format": "html", "images": [IMAGE]})
    )
    await hass.async_start()
    await early
    bot = hass.data[DOMAIN]
    assert bot._client.olm is not None, "encryption is not active"
    first_device = bot._client.device_id
    assert first_device != legacy_device, "kept a device that has no keys on disk"
    assert await bot_devices() == [first_device], "the keyless device was not removed"
    assert bot._is_encrypted_room(encrypted_room)
    assert not bot._is_encrypted_room(plain_room)

    events = await collect(human, encrypted_room, 2)
    texts = [e for e in events if isinstance(e, RoomMessageText)]
    images = [e for e in events if isinstance(e, RoomEncryptedImage)]
    assert len(texts) == 1 and len(images) == 1, events
    assert texts[0].decrypted, "text was not sent encrypted"
    assert texts[0].body == PLAIN, texts[0].body
    assert texts[0].formatted_body == HTML, texts[0].formatted_body
    assert images[0].decrypted, "image event was not sent encrypted"
    download = await human.download(mxc=images[0].url)
    assert download.body != image_bytes, "the uploaded file is not encrypted"
    assert (
        decrypt_attachment(
            download.body,
            images[0].key["k"],
            images[0].hashes["sha256"],
            images[0].iv,
        )
        == image_bytes
    ), "decrypted image differs from the original"
    print("ok  encrypted room: text and image sent before startup arrive encrypted")

    # --- Unencrypted rooms keep working as before.
    await send(hass, plain_room, HTML, {"format": "html", "images": [IMAGE]})
    events = await collect(human, plain_room, 2)
    texts = [e for e in events if isinstance(e, RoomMessageText)]
    images = [e for e in events if isinstance(e, RoomMessageImage)]
    assert len(texts) == 1 and len(images) == 1, events
    assert not texts[0].decrypted and texts[0].body == PLAIN
    download = await human.download(mxc=images[0].url)
    assert download.body == image_bytes
    print("ok  unencrypted room: text and image sent in the clear")

    # --- A room the bot is not in is refused before anything is uploaded.
    await send(hass, "!nosuchroom:example.com", "nope", {"images": [IMAGE]})
    assert logged("'!nosuchroom:example.com': the bot is not in this room")
    print("ok  unknown room refused")

    # --- An encrypted command from the human reaches Home Assistant.
    commands: list = []
    hass.bus.async_listen(EVENT_MATRIX_COMMAND, commands.append)
    await human.room_send(
        encrypted_room,
        "m.room.message",
        {"msgtype": "m.text", "body": "!ping now"},
        ignore_unverified_devices=True,
    )
    for _ in range(40):
        await asyncio.sleep(0.5)
        if commands:
            break
    assert commands and commands[0].data["command"] == "ping", commands
    assert commands[0].data["args"] == ["now"]
    print("ok  encrypted command decrypted and fired as matrix_command")

    # --- Restart: same device, same keys, messages still decrypt.
    await hass.async_stop(force=True)
    hass = await start_hass([encrypted_room, plain_room])
    bot = hass.data[DOMAIN]
    assert bot._client.device_id == first_device, "device changed across restart"
    await send(hass, encrypted_room, "after restart", {})
    events = await collect(human, encrypted_room, 1)
    assert [e.body for e in events if isinstance(e, RoomMessageText)] == [
        "after restart"
    ], events
    assert events[0].decrypted
    print("ok  restart: same device, message still decrypts")

    # --- The token stops working: the password login returns as the same
    # --- device, so its keys stay valid.
    await hass.async_stop(force=True)
    with open(f"{CONFIG_DIR}/.matrix.conf") as conf:
        session = json.load(conf)
    session[BOT] = "not-a-valid-token"
    with open(f"{CONFIG_DIR}/.matrix.conf", "w") as conf:
        json.dump(session, conf)
    hass = await start_hass([encrypted_room, plain_room])
    bot = hass.data[DOMAIN]
    assert bot._client.device_id == first_device, "new device after token loss"
    await send(hass, encrypted_room, "after token loss", {})
    events = await collect(human, encrypted_room, 1)
    assert [e.body for e in events if isinstance(e, RoomMessageText)] == [
        "after token loss"
    ], events
    assert await bot_devices() == [first_device]
    print("ok  token lost: password login returns as the same device")

    # --- The key store breaks: nothing goes to the encrypted room.
    await hass.async_stop(force=True)
    store_file = f"{CONFIG_DIR}/.matrix_store/{BOT}_{first_device}.db"
    with open(store_file, "wb") as store:
        store.write(b"this is not a database")
    hass = await start_hass([encrypted_room, plain_room])
    assert hass.data[DOMAIN]._client.olm is None
    assert logged("Unable to open the encryption key store")
    await send(hass, encrypted_room, "must not arrive", {"images": [IMAGE]})
    assert await collect(human, encrypted_room, 1, rounds=5) == []
    await send(hass, plain_room, "still works", {})
    events = await collect(human, plain_room, 1)
    assert [e.body for e in events] == ["still works"], events
    print("ok  broken key store: encrypted room refused, unencrypted room works")

    await hass.async_stop(force=True)
    await human.close()

    expected = (
        "has no encryption keys on disk",
        "Restoring login from access token failed",
        "the bot is not in this room",
        "Unable to open the encryption key store",
        "the room is encrypted and encryption is unavailable",
    )
    problems = [
        r
        for r in records
        if r.levelno >= logging.WARNING
        and ("matrix" in r.name or "blocking call" in r.getMessage().lower())
        and not any(text in r.getMessage() for text in expected)
        # This script's own file access is not the integration's.
        and "tests/e2e_live.py" not in r.getMessage()
    ]
    for record in problems:
        print("LOG", record.levelname, record.name, record.getMessage()[:300])
    assert not problems, "unexpected warnings or errors were logged"
    print("e2e ok")


asyncio.run(main())
