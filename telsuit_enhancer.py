import re
from telethon import TelegramClient, events
from telethon.tl.types import MessageEntityCustomEmoji
from telsuit_core import get_config, logger
from telsuit_cleaner import run_duplicate_check_for_event


# --- 🎨 Emoji Enhancer Logic ---
async def start_enhancer(auto=False):
    """Main entry point for emoji enhancement."""
    config = get_config()

    if not config["admins"]:
        print("⚠️ No admins configured.")
        return

    if not config["channels"]:
        print("⚠️ No channels configured.")
        return

    admins = list(config["admins"].keys())

    # Auto-select admin for background/headless mode
    if auto:
        selected_admin = admins[0]
        print(f"🤖 Auto-selected admin: {selected_admin}")
    else:
        print("\n--- Available Admins ---")
        for i, phone in enumerate(admins, start=1):
            print(f"{i}. {phone}")
        sel = input("Select which admin to use: ").strip()
        if not sel.isdigit() or int(sel) < 1 or int(sel) > len(admins):
            print("Invalid selection.")
            return
        selected_admin = admins[int(sel) - 1]

    creds = config["admins"][selected_admin]
    api_id, api_hash, phone = creds["api_id"], creds["api_hash"], selected_admin

    client = TelegramClient(f"enhancer_{phone}.session", int(api_id), api_hash)

    # --- Event Handler ---
    async def handle_message(event):
        """Enhance emojis in new or edited messages."""
        text = event.message.text
        if not text:
            return

        try:
            parsed_text, parsed_entities = await client._parse_message_text(text, 'md')
        except TypeError:
            parsed_text, parsed_entities = await client._parse_message_text(
                text=text, parse_mode='md'
            )

        matches = []
        for emoji, doc_id in config['emoji_map'].items():
            for m in re.finditer(re.escape(emoji), parsed_text):
                matches.append((m.start(), m.end(), emoji, int(doc_id)))

        if not matches:
            return

        matches.sort(key=lambda x: x[0])
        new_entities = []

        for start, end, emoji, doc_id in matches:
            prefix = parsed_text[:start]
            offset = len(prefix.encode('utf-16-le')) // 2
            length = len(emoji.encode('utf-16-le')) // 2
            new_entities.append(
                MessageEntityCustomEmoji(
                    offset=offset, length=length, document_id=doc_id
                )
            )

        final_entities = (parsed_entities or []) + new_entities
        final_entities.sort(key=lambda e: e.offset)

        try:
            await event.edit(parsed_text, formatting_entities=final_entities)
            logger.info(f"✅ Enhanced message {event.message.id} in {event.chat.username}")
        except Exception as e:
            logger.error(f"❌ Failed editing message {event.message.id}: {e}")
        finally:
            try:
                # ✅ Trigger Cleaner only for real NEW posts
                msg = event.message

                # Skip if message has edit_date (means it's an edited post)
                if getattr(msg, "edit_date", None):
                    logger.debug(
                        f"✏️ Edit detected for message {msg.id} — cleaner not triggered"
                    )
                    return

                # Skip if not from a channel
                if not getattr(event, "is_channel", False):
                    logger.debug(
                        f"💬 Non-channel message ({msg.id}) — cleaner not triggered"
                    )
                    return

                # Run cleaner only for true new messages
                await run_duplicate_check_for_event(client, config, event)
                logger.info(
                    f"🧹 Cleaner triggered after NEW message {msg.id} in {event.chat.username}"
                )

            except Exception as clean_err:
                logger.error(f"Cleaner trigger failed: {clean_err}")

    # --- Register handlers ---
    for ch in config["channels"]:
        client.add_event_handler(handle_message, events.NewMessage(chats=ch))
        client.add_event_handler(handle_message, events.MessageEdited(chats=ch))
        logger.info(f"Monitoring channel: {ch}")

    await client.start(phone=phone)
    logger.info(f"Client started under admin {phone}")
    await client.run_until_disconnected()


# --- ▶️ CLI Entrypoint ---
async def run_enhancer(auto=False):
    """Wrapper for async run (used by main.py)."""
    await start_enhancer(auto=auto)
