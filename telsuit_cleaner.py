from datetime import datetime, timedelta
import asyncio
from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events
from telethon.tl.types import Message
from telsuit_core import (
    get_config,
    logger,
    print_section,
    print_warning,
    print_success,
)


# --- Logging: ensure rotating file handler to avoid log bloat ---
def _ensure_rotating_logs() -> None:
    """Swap any plain FileHandler with RotatingFileHandler (1MB x 3 files)."""
    need_add = True
    for h in list(logger.handlers):
        if isinstance(h, RotatingFileHandler):
            need_add = False
        # Replace plain FileHandler target with rotating version
        if getattr(h, "baseFilename", None) and not isinstance(
            h, RotatingFileHandler
        ):
            logger.removeHandler(h)
    if need_add:
        rotating = RotatingFileHandler(
            filename="telsuit.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        rotating.setFormatter(
            logger.handlers[0].formatter if logger.handlers else None
        )
        logger.addHandler(rotating)


_ensure_rotating_logs()


# ---------------------------
# Internal helpers
# ---------------------------
async def _delete_messages(client: TelegramClient, chat_id, msg_ids) -> int:
    deleted = 0
    if not msg_ids:
        return deleted
    # Delete in small batches to be kind to Telegram limits
    batch = []
    for mid in msg_ids:
        batch.append(mid)
        if len(batch) >= 50:
            await client.delete_messages(chat_id, batch)
            deleted += len(batch)
            batch = []
            await asyncio.sleep(0.5)
    if batch:
        await client.delete_messages(chat_id, batch)
        deleted += len(batch)
    return deleted


async def _search_duplicates(
    client: TelegramClient, chat_id, keyword: str, keep_latest_id: int | None
) -> list[int]:
    """
    Find duplicate messages that contain `keyword`.
    Returns a list of message IDs to delete (excluding `keep_latest_id`).
    """
    ids = []
    async for msg in client.iter_messages(chat_id, search=keyword, limit=300):
        if isinstance(msg, Message) and msg.id != keep_latest_id:
            # Basic heuristic: has text and keyword substring
            text = (msg.raw_text or "").lower()
            if keyword.lower() in text:
                ids.append(msg.id)
    return ids


# --------------------------------------------
# Public: trigger from the Enhancer after edit
# --------------------------------------------
async def run_duplicate_check_for_event(
    client: TelegramClient, config: dict, event
) -> None:
    """
    Lightweight duplicate sweep to be called by the Enhancer AFTER it edits a
    message. It will:
      - Check cleaner keywords in the new message
      - Search for older posts with that keyword
      - Delete older duplicates, keep current
    """
    cleaner_cfg = config.get("cleaner", {})
    keywords = cleaner_cfg.get("keywords", [])
    if not keywords:
        return

    msg: Message = event.message
    text = (msg.raw_text or "").strip()
    if not text:
        return

    # Find first matching keyword inside the message to drive the search
    matched_kw = None
    for kw in keywords:
        if kw and kw.lower() in text.lower():
            matched_kw = kw
            break
    if not matched_kw:
        return

    chat_id = event.chat_id
    try:
        dup_ids = await _search_duplicates(
            client=client,
            chat_id=chat_id,
            keyword=matched_kw,
            keep_latest_id=msg.id,
        )
        if not dup_ids:
            return

        deleted = await _delete_messages(client, chat_id, dup_ids)
        if deleted:
            logger.info(
                "Cleaner (auto): removed %d duplicates for keyword '%s' "
                "in chat %s (kept %s).",
                deleted,
                matched_kw,
                chat_id,
                msg.id,
            )
    except Exception as exc:
        logger.error("Cleaner (auto) failed: %s", exc)


# --------------------------------------------
# Interactive Cleaner (menu-driven)
# --------------------------------------------
async def _menu_remove_duplicates(client: TelegramClient, chat_id) -> None:
    kw = input("Keyword / SKU to deduplicate by: ").strip()
    if not kw:
        print("No keyword entered.")
        return
    print("Searching duplicates...")
    dup_ids = await _search_duplicates(client, chat_id, kw, keep_latest_id=None)
    if not dup_ids:
        print_success("No duplicates found.")
        return

    # Keep the newest one (highest id), delete the rest
    keep_id = max(dup_ids)
    to_delete = [mid for mid in dup_ids if mid != keep_id]
    deleted = await _delete_messages(client, chat_id, to_delete)
    print_success(f"Deleted {deleted} messages. Kept newest id: {keep_id}")


async def _menu_delete_by_keyword(client: TelegramClient, chat_id) -> None:
    kw = input("Keyword to delete: ").strip()
    if not kw:
        print("No keyword entered.")
        return
    limit_str = input("How many recent messages to scan? [default 200]: ").strip()
    try:
        limit = int(limit_str) if limit_str else 200
    except ValueError:
        limit = 200

    ids = []
    async for msg in client.iter_messages(chat_id, limit=limit):
        text = (msg.raw_text or "")
        if kw.lower() in text.lower():
            ids.append(msg.id)
    if not ids:
        print_warning("Nothing matched.")
        return
    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages containing '{kw}'.")


async def _menu_delete_by_age(client: TelegramClient, chat_id) -> None:
    days_str = input("Delete messages older than N days: ").strip()
    try:
        days = int(days_str)
    except ValueError:
        print("Invalid number.")
        return
    cutoff = datetime.utcnow() - timedelta(days=days)

    ids = []
    async for msg in client.iter_messages(chat_id, limit=500):
        if msg.date and msg.date.replace(tzinfo=None) < cutoff:
            ids.append(msg.id)

    if not ids:
        print_warning("No messages older than that.")
        return
    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages older than {days} days.")


async def _menu_forward_copy(client: TelegramClient, chat_id) -> None:
    target = input("Target channel (e.g. @mytarget): ").strip()
    if not target:
        print("No target provided.")
        return
    count_str = input("How many most recent messages to send? [default 10]: ").strip()
    try:
        count = int(count_str) if count_str else 10
    except ValueError:
        count = 10

    mode = input("Mode: (F)orward or (C)opy text only? [F/C]: ").strip().lower()
    sent = 0
    async for msg in client.iter_messages(chat_id, limit=count):
        try:
            if mode == "c":
                text = msg.raw_text or ""
                if text:
                    await client.send_message(target, text)
                    sent += 1
            else:
                await client.forward_messages(target, msg)
                sent += 1
            await asyncio.sleep(0.3)
        except Exception as exc:
            logger.error("Forward/copy failed for %s: %s", msg.id, exc)
    print_success(f"Sent {sent} messages to {target}.")


def _pick_channel(config: dict) -> str | None:
    channels = config.get("channels", [])
    if not channels:
        print_warning("No channels configured.")
        return None
    print("\n--- Configured Channels ---")
    for i, ch in enumerate(channels, start=1):
        print(f"{i}. {ch}")
    sel = input("Select channel: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(channels)):
        print("Invalid selection.")
        return None
    return channels[int(sel) - 1]


async def _interactive_menu(client: TelegramClient, config: dict) -> None:
    while True:
        print_section("Channel Cleaner Menu")
        print("1️⃣  Remove duplicate posts")
        print("2️⃣  Delete by keyword")
        print("3️⃣  Delete by date (older than N days)")
        print("4️⃣  Forward / Copy recent posts")
        print("5️⃣  View cleaner settings")
        print("6️⃣  Start automatic monitoring (new posts)")
        print("7️⃣  Return to TelSuit menu")

        choice = input("Select option: ").strip()

        if choice == "1":
            ch = _pick_channel(config)
            if ch:
                await _menu_remove_duplicates(client, ch)

        elif choice == "2":
            ch = _pick_channel(config)
            if ch:
                await _menu_delete_by_keyword(client, ch)

        elif choice == "3":
            ch = _pick_channel(config)
            if ch:
                await _menu_delete_by_age(client, ch)

        elif choice == "4":
            ch = _pick_channel(config)
            if ch:
                await _menu_forward_copy(client, ch)

        elif choice == "5":
            cleaner_cfg = config.get(
                "cleaner", {"keywords": [], "forward_channels": [], "delete_rules": {}}
            )
            print("\n--- Cleaner Settings ---")
            kws = cleaner_cfg.get("keywords", [])
            fwd = cleaner_cfg.get("forward_channels", [])
            rules = cleaner_cfg.get("delete_rules", {})
            print(f"Keywords: {kws or '[]'}")
            print(f"Forward channels: {fwd or '[]'}")
            print(f"Delete rules: {rules or '{}'}")

        elif choice == "6":
            print("Starting live monitor for NEW posts only. Ctrl+C to stop.")
            await _start_live_monitor(client, config)
            # When monitor returns (Ctrl+C), loop back to menu

        elif choice == "7":
            print("Returning to TelSuit...")
            break

        else:
            print("Invalid option.")


# --------------------------------------------
# Live monitor: NEW posts only (interactive)
# --------------------------------------------
async def _start_live_monitor(client: TelegramClient, config: dict) -> None:
    async def on_new_message(event):
        msg = event.message
        if not msg or not (msg.raw_text or "").strip():
            return
        # Auto duplicate sweep based on configured keywords
        await run_duplicate_check_for_event(client, config, event)

    for ch in config.get("channels", []):
        client.add_event_handler(on_new_message, events.NewMessage(chats=ch))
        logger.info("Cleaner live-monitoring new posts in: %s", ch)

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\nStopped live monitor.")


# --------------------------------------------
# Public Entrypoints
# --------------------------------------------
async def start_cleaner(auto: bool = False) -> None:
    """
    Main cleaner entry point.
      * auto=False → open interactive menu
      * auto=True  → headless: live monitor for new posts (service usage)
    """
    config = get_config()
    admins = list(config.get("admins", {}).keys())
    if not admins:
        print_warning("No admins configured.")
        return

    selected_admin = admins[0]
    print(f"🤖 Auto-selected admin: {selected_admin}")
    creds = config["admins"][selected_admin]
    api_id, api_hash = int(creds["api_id"]), creds["api_hash"]

    client = TelegramClient(f"cleaner_{selected_admin}.session", api_id, api_hash)
    await client.start(phone=selected_admin)
    logger.info("Cleaner client started under admin %s", selected_admin)

    if auto:
        await _start_live_monitor(client, config)
    else:
        await _interactive_menu(client, config)


async def run_cleaner(config: dict | None = None, auto: bool = False) -> None:
    """
    Wrapper used by TelSuit main menu.
    Config param is accepted for API symmetry but is reloaded inside to ensure
    fresh state when called headless from systemd as well.
    """
    await start_cleaner(auto=auto)
