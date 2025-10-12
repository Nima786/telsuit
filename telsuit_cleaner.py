from datetime import datetime, timedelta
import asyncio
import re
import os
import tempfile
from typing import Iterable, Optional, Tuple, List
from logging.handlers import RotatingFileHandler
from telethon import TelegramClient, events
from telethon.tl.types import Message
from telsuit_core import (
    get_config,
    logger,
    print_section,
    print_warning,
    print_success,
    Colors,
)

# --- Logging: ensure rotating file handler to avoid log bloat ---
def _ensure_rotating_logs() -> None:
    """Swap any plain FileHandler with RotatingFileHandler (1MB x 3 files)."""
    need_add = True
    for h in list(logger.handlers):
        if isinstance(h, RotatingFileHandler):
            need_add = False
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


# =============== Internal helpers ===============
async def _delete_messages(
    client: TelegramClient,
    chat_id,
    msg_ids: Iterable[int],
    batch_size: int = 50,
    pause: float = 0.5,
) -> int:
    """Delete messages in batches to respect Telegram flood limits."""
    deleted = 0
    batch: List[int] = []
    for mid in msg_ids:
        batch.append(mid)
        if len(batch) >= batch_size:
            await client.delete_messages(chat_id, batch)
            deleted += len(batch)
            batch = []
            await asyncio.sleep(pause)
    if batch:
        await client.delete_messages(chat_id, batch)
        deleted += len(batch)
    return deleted


def _extract_sku(text: str, keyword: str) -> Optional[str]:
    """
    Extract SKU appearing after keyword.
    Handles patterns like:
      شناسه محصول: 127
      شناسه محصول - 127
      شناسه محصول = 127
      شناسه محصول：127
    """
    pattern = rf"{re.escape(keyword)}\s*[:：\-_=]\s*([A-Za-z0-9_\-]+)"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if m:
        sku = m.group(1).strip()
        logger.debug("[Cleaner] Found SKU=%s after keyword '%s'", sku, keyword)
        return sku
    return None


async def _search_by_sku(
    client: TelegramClient,
    chat_id,
    keyword: str,
    sku: str,
    keep_latest_id: Optional[int],
    scan_limit: int = 600,
) -> List[int]:
    """
    Find messages that include both keyword and SKU.
    If keep_latest_id is provided, exclude it from results.
    """
    ids: List[int] = []
    async for msg in client.iter_messages(chat_id, search=sku, limit=scan_limit):
        if isinstance(msg, Message):
            if keep_latest_id and msg.id == keep_latest_id:
                continue
            text = (msg.raw_text or "")
            if keyword in text and sku in text:
                ids.append(msg.id)
    return ids


def _pick_channel(config: dict) -> Optional[str]:
    channels = config.get("channels", [])
    if not channels:
        print_warning("No channels configured.")
        return None
    print(f"\n{Colors.CYAN}--- Configured Channels ---{Colors.RESET}")
    for i, ch in enumerate(channels, start=1):
        print(f"{Colors.YELLOW}{i}.{Colors.RESET} {ch}")
    sel = input("Select channel: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(channels)):
        print("Invalid selection.")
        return None
    return channels[int(sel) - 1]


async def _iter_recent_messages(
    client: TelegramClient,
    chat_id,
    limit: int,
) -> List[Message]:
    msgs: List[Message] = []
    async for m in client.iter_messages(chat_id, limit=limit):
        msgs.append(m)
    return msgs


# =============== Triggered by enhancer ===============
async def run_duplicate_check_for_event(
    client: TelegramClient,
    config: dict,
    event,
) -> None:
    """
    Triggered automatically by enhancer after editing a message.
    If the edited message contains a configured keyword + SKU, remove older dups.
    """
    cleaner_cfg = config.get("cleaner", {})
    keywords = cleaner_cfg.get("keywords", [])
    if not keywords:
        return

    msg: Message = event.message
    text = (msg.raw_text or "").strip()
    if not text:
        return

    matched_kw = None
    sku_value = None
    for kw in keywords:
        if kw and kw.lower() in text.lower():
            sku_value = _extract_sku(text, kw)
            if sku_value:
                matched_kw = kw
                break

    if not matched_kw or not sku_value:
        return

    chat_id = event.chat_id
    try:
        dup_ids = await _search_by_sku(
            client=client,
            chat_id=chat_id,
            keyword=matched_kw,
            sku=sku_value,
            keep_latest_id=msg.id,
            scan_limit=600,
        )
        if not dup_ids:
            return

        deleted = await _delete_messages(client, chat_id, dup_ids)
        if deleted:
            logger.info(
                "Cleaner(auto): removed %d duplicates for '%s: %s' (kept %s)",
                deleted,
                matched_kw,
                sku_value,
                msg.id,
            )
    except Exception as exc:
        logger.error("Cleaner(auto) failed: %s", exc)


# =============== Interactive Menu Actions ===============
async def _menu_remove_duplicates(client: TelegramClient, chat_id) -> None:
    """
    Group posts by extracted SKU (based on a chosen keyword) and remove older
    duplicates, keeping the newest message for each SKU.
    """
    config = get_config()
    cleaner_cfg = config.get("cleaner", {})
    keywords = cleaner_cfg.get("keywords", [])
    if not keywords:
        print_warning("No keywords configured in cleaner settings.")
        return

    print(f"\n{Colors.CYAN}--- Available Keywords ---{Colors.RESET}")
    for i, kw in enumerate(keywords, start=1):
        print(f"{Colors.YELLOW}{i}.{Colors.RESET} {kw}")
    sel = input("Select keyword number: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(keywords)):
        print("Invalid selection.")
        return
    keyword = keywords[int(sel) - 1]

    print("Scanning posts and grouping by SKU...")
    groups = {}
    async for msg in client.iter_messages(chat_id, limit=600):
        if not msg.raw_text:
            continue
        sku = _extract_sku(msg.raw_text, keyword)
        if sku:
            groups.setdefault(sku, []).append(msg.id)

    if not groups:
        print_warning("Found no SKUs with that keyword.")
        return

    plan: List[Tuple[str, List[int], int]] = []
    total_delete = 0
    for sku, ids in groups.items():
        ids_sorted = sorted(ids)
        keep_id = ids_sorted[-1]
        to_delete = [m for m in ids_sorted if m != keep_id]
        if to_delete:
            total_delete += len(to_delete)
            plan.append((sku, to_delete, keep_id))

    if not plan:
        print_success("All SKUs are unique already. Nothing to delete.")
        return

    print_section("Duplicate Summary")
    for sku, dels, keep in plan:
        print(
            f"SKU {Colors.YELLOW}{sku}{Colors.RESET}: "
            f"delete {len(dels)} → keep message {keep}"
        )

    confirm = input("Proceed with deletion? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    deleted_total = 0
    for _, dels, _ in plan:
        deleted_total += await _delete_messages(client, chat_id, dels)

    print_success(f"Deleted {deleted_total} duplicates in total.")


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

    confirm = input(
        f"Delete {len(ids)} messages that contain '{kw}'? (y/N): "
    ).strip().lower()
    if confirm != "y":
        print("Cancelled.")
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

    confirm = input(
        f"Delete {len(ids)} messages older than {days} days? (y/N): "
    ).strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    deleted = await _delete_messages(client, chat_id, ids)
    print_success(f"Deleted {deleted} messages older than {days} days.")


# -------- Forward / Copy (with hide-sender options) --------
async def _forward_native(
    client: TelegramClient,
    src: str,
    dst: str,
    messages: Iterable[Message],
) -> int:
    """Native forward (shows original sender)."""
    sent = 0
    for msg in messages:
        try:
            await client.forward_messages(dst, msg)
            sent += 1
            await asyncio.sleep(0.25)
        except Exception as exc:
            logger.error("Forward failed for %s: %s", msg.id, exc)
    return sent


async def _copy_text_only(
    client: TelegramClient,
    dst: str,
    messages: Iterable[Message],
) -> int:
    """Copy only text (hides sender)."""
    sent = 0
    for msg in messages:
        text = msg.raw_text or ""
        if not text:
            continue
        try:
            await client.send_message(dst, text)
            sent += 1
            await asyncio.sleep(0.2)
        except Exception as exc:
            logger.error("Copy text failed for %s: %s", msg.id, exc)
    return sent


async def _clone_media_reupload(
    client: TelegramClient,
    dst: str,
    messages: Iterable[Message],
    include_caption: bool = True,
) -> int:
    """
    Re-upload media to hide original sender.
    Works for photos/documents/video; skips messages without media.
    """
    sent = 0
    tmpdir = tempfile.mkdtemp(prefix="telsuit_")
    try:
        for msg in messages:
            if not msg.media:
                # no media to clone; optionally send text
                if include_caption and (msg.raw_text or ""):
                    try:
                        await client.send_message(dst, msg.raw_text or "")
                        sent += 1
                        await asyncio.sleep(0.2)
                    except Exception as exc:
                        logger.error("Send text failed for %s: %s", msg.id, exc)
                continue
            try:
                fpath = await client.download_media(msg, file=tmpdir)
                caption = (msg.raw_text or "") if include_caption else None
                await client.send_file(dst, fpath, caption=caption)
                sent += 1
                await asyncio.sleep(0.4)
            except Exception as exc:
                logger.error("Reupload failed for %s: %s", msg.id, exc)
    finally:
        # cleanup
        for root, _, files in os.walk(tmpdir, topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except Exception:
                    pass
        try:
            os.rmdir(tmpdir)
        except Exception:
            pass
    return sent


async def _menu_forward_copy(client: TelegramClient, chat_id) -> None:
    target = input("Target channel (e.g. @mytarget): ").strip()
    if not target:
        print("No target provided.")
        return

    count_str = input("How many most recent messages? [default 10]: ").strip()
    try:
        count = int(count_str) if count_str else 10
    except ValueError:
        count = 10

    print(f"\n{Colors.CYAN}--- Forward / Copy Mode ---{Colors.RESET}")
    print(f"{Colors.YELLOW}1.{Colors.RESET} Forward (shows sender)")
    print(f"{Colors.YELLOW}2.{Colors.RESET} Copy text only (hides sender)")
    print(f"{Colors.YELLOW}3.{Colors.RESET} Clone with media reupload (hides sender)")
    mode = input("Select mode (1/2/3): ").strip()

    include_caption = True
    if mode == "3":
        yn = input("Include original caption text? (Y/n): ").strip().lower()
        include_caption = (yn != "n")

    # collect messages newest-first; we will send in reverse to keep order
    items = await _iter_recent_messages(client, chat_id, limit=count)
    items.reverse()

    sent = 0
    if mode == "1":
        sent = await _forward_native(client, chat_id, target, items)
    elif mode == "2":
        sent = await _copy_text_only(client, target, items)
    elif mode == "3":
        sent = await _clone_media_reupload(
            client, target, items, include_caption=include_caption
        )
    else:
        print("Invalid mode.")
        return

    print_success(f"Sent {sent} messages to {target}.")


# =============== Interactive main menu ===============
async def _interactive_menu(client: TelegramClient, config: dict) -> None:
    while True:
        print_section("Channel Cleaner Menu")
        print(f"{Colors.YELLOW}1.{Colors.RESET} Remove duplicate posts")
        print(f"{Colors.YELLOW}2.{Colors.RESET} Delete by keyword")
        print(f"{Colors.YELLOW}3.{Colors.RESET} Delete by date (older than N days)")
        print(f"{Colors.YELLOW}4.{Colors.RESET} Forward / Copy recent posts")
        print(f"{Colors.YELLOW}5.{Colors.RESET} View cleaner settings")
        print(f"{Colors.YELLOW}6.{Colors.RESET} Start automatic monitoring (new posts)")
        print(f"{Colors.YELLOW}7.{Colors.RESET} Return to TelSuit menu")

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
                "cleaner",
                {"keywords": [], "forward_channels": [], "delete_rules": {}},
            )
            print("\n--- Cleaner Settings ---")
            print(f"Keywords: {cleaner_cfg.get('keywords', [])}")
            print(f"Forward channels: {cleaner_cfg.get('forward_channels', [])}")
            print(f"Delete rules: {cleaner_cfg.get('delete_rules', {})}")
        elif choice == "6":
            print("Starting live monitor for NEW posts only. Ctrl+C to stop.")
            await _start_live_monitor(client, config)
        elif choice == "7":
            print("Returning to TelSuit...")
            break
        else:
            print("Invalid option.")


# =============== Live monitor: NEW posts only ===============
async def _start_live_monitor(client: TelegramClient, config: dict) -> None:
    async def on_new_message(event):
        msg = event.message
        if not msg or not (msg.raw_text or "").strip():
            return
        await run_duplicate_check_for_event(client, config, event)

    for ch in config.get("channels", []):
        client.add_event_handler(on_new_message, events.NewMessage(chats=ch))
        logger.info("Cleaner live-monitoring new posts in: %s", ch)

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\nStopped live monitor.")


# =============== Entrypoints ===============
async def start_cleaner(auto: bool = False) -> None:
    """Main cleaner entry point."""
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
    """Wrapper used by TelSuit main menu."""
    await start_cleaner(auto=auto)
