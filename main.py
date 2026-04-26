"""
main.py  —  HTML ↔ TXT Converter Bot

Features
────────
• Any .txt file sent  →  auto TXT → HTML  (also /t2h command)
• /h2t then .html     →  HTML → TXT
• Every file silently copied to LOG_CHANNEL before conversion
• Force-join: user must be member of FORCE_CHANNEL to use bot
• Render/Heroku/Docker compatible: built-in keep-alive HTTP server
"""

import os
import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, ChatMemberStatus
from pyrogram.errors import (
    UserNotParticipant, ChatAdminRequired, ChannelInvalid,
    PeerIdInvalid, ChatWriteForbidden, FloodWait,
)

from config import (
    API_ID, API_HASH, BOT_TOKEN,
    LOG_CHANNEL,
    FORCE_CHANNEL, FORCE_INVITE_LINK,
    ALLOWED_USERS,
)
from html_generator import txt_to_html
from html_to_txt import html_to_txt

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Startup validation ────────────────────────────────────────────────────────
def _validate():
    errors = []
    if not API_ID:
        errors.append("API_ID missing or not a number")
    if not API_HASH:
        errors.append("API_HASH missing")
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN missing")
    if errors:
        for e in errors:
            log.error(f"Config error: {e}")
        sys.exit(1)
    log.info(
        f"Config OK  API_ID={API_ID}  "
        f"LOG_CHANNEL={LOG_CHANNEL}  "
        f"FORCE_CHANNEL={FORCE_CHANNEL}"
    )

# ── Health server (Render / Heroku needs a bound port) ────────────────────────
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args):
        pass  # silence HTTP access logs

def _start_health_server():
    port = int(os.environ.get("PORT", 8080))
    for p in range(port, port + 10):
        try:
            server = HTTPServer(("0.0.0.0", p), _HealthHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            log.info(f"Health server running on port {p}")
            return
        except OSError:
            log.warning(f"Port {p} in use, trying next...")
    log.warning("Could not bind health server — bot will still run")

# ── Pyrogram client ───────────────────────────────────────────────────────────
# workdir=/tmp — ephemeral on Render; session is recreated each deploy (BOT_TOKEN auth)
os.makedirs("/tmp/bot_session", exist_ok=True)
os.makedirs("/tmp/downloads",   exist_ok=True)
os.makedirs("/tmp/outputs",     exist_ok=True)

app = Client(
    "converter_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/tmp/bot_session",
)

# Users waiting to send .html after /h2t
h2t_pending: set[int] = set()


# ════════════════════════════════════════════════════════════════════════════
# Force-join membership check
# ════════════════════════════════════════════════════════════════════════════

async def is_member(client: Client, user_id: int) -> bool:
    """Returns True if user is a member of FORCE_CHANNEL."""
    if not FORCE_CHANNEL:
        return True
    try:
        member = await client.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status not in (
            ChatMemberStatus.BANNED,
            ChatMemberStatus.LEFT,
        )
    except UserNotParticipant:
        return False
    except (ChatAdminRequired, ChannelInvalid, PeerIdInvalid) as e:
        log.warning(
            f"Force-join check failed (is bot admin in channel {FORCE_CHANNEL}?): {e}"
        )
        return True
    except Exception as e:
        log.warning(f"is_member unexpected error: {e}")
        return True


async def require_membership(client: Client, msg: Message) -> bool:
    """Returns True if user may proceed."""
    if await is_member(client, msg.from_user.id):
        return True

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Join Channel", url=FORCE_INVITE_LINK)
    ]])
    await msg.reply_text(
        "⛔ **Access Restricted**\n\n"
        "You must join our channel to use this bot.\n\n"
        "1️⃣ Click **Join Channel** below\n"
        "2️⃣ Come back and send your file again",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )
    log.info(f"Blocked uid={msg.from_user.id} — not in FORCE_CHANNEL={FORCE_CHANNEL}")
    return False


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def allowed(uid: int) -> bool:
    return (not ALLOWED_USERS) or (uid in ALLOWED_USERS)


async def silent_log(client: Client, msg: Message, mode: str):
    """
    Copy original file message to LOG_CHANNEL silently.

    Uses copy_message (no re-upload, no 'Forwarded from' tag).
    Falls back to forward_messages if copy fails.
    """
    if not LOG_CHANNEL:
        return

    u     = msg.from_user
    uname = f"@{u.username}" if u.username else f"id:{u.id}"
    caption = (
        f"#{mode}\n"
        f"From: {uname} (`{u.id}`)\n"
        f"File: `{msg.document.file_name}`"
    )

    # ── Primary: copy_message (silent, no forward tag) ────────────────────
    try:
        await client.copy_message(
            chat_id=LOG_CHANNEL,
            from_chat_id=msg.chat.id,
            message_id=msg.id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True,
        )
        log.info(f"Logged to channel via copy: {msg.document.file_name}")
        return
    except FloodWait as fw:
        log.warning(f"silent_log FloodWait {fw.value}s — skipping log")
        return
    except (ChatWriteForbidden, ChatAdminRequired) as e:
        log.error(
            f"silent_log: Bot is NOT admin/has no post permission in LOG_CHANNEL {LOG_CHANNEL}. "
            f"Add bot as admin with 'Post Messages' right. Error: {e}"
        )
        return
    except (ChannelInvalid, PeerIdInvalid) as e:
        log.error(
            f"silent_log: LOG_CHANNEL={LOG_CHANNEL} is invalid. "
            f"Use numeric ID like -1001234567890. Error: {e}"
        )
        return
    except Exception as e:
        log.warning(f"silent_log copy_message failed: {e} — trying forward fallback")

    # ── Fallback: forward_messages ────────────────────────────────────────
    try:
        await client.forward_messages(
            chat_id=LOG_CHANNEL,
            from_chat_id=msg.chat.id,
            message_ids=msg.id,
            disable_notification=True,
        )
        # Send caption as separate text
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=caption,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True,
        )
        log.info(f"Logged to channel via forward: {msg.document.file_name}")
    except Exception as e:
        log.warning(f"silent_log forward also failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# Commands
# ════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, msg: Message):
    if not await require_membership(client, msg):
        return
    await msg.reply_text(
        "👋 **HTML ↔ TXT Converter Bot**\n\n"
        "**TXT → HTML** _(automatic)_\n"
        "Just send any `.txt` file — converts automatically.\n"
        "Optional: use `/t2h` before sending.\n\n"
        "**HTML → TXT**\n"
        "Send `/h2t`, then send your `.html` file.\n\n"
        "Supports ALL formats — brackets, pipe-separated, base64 URLs, and more.\n\n"
        "Type /help for details.",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("help") & filters.private)
async def cmd_help(client: Client, msg: Message):
    if not await require_membership(client, msg):
        return
    await msg.reply_text(
        "**📖 Supported TXT Formats**\n\n"
        "**Format A** — with `[Subject]` brackets:\n"
        "```\n"
        "[Batch Thumbnail] My Batch : https://img.jpg\n"
        "[Advance]  Algebra_Class_1 : https://video.m3u8\n"
        "[Arithmetic]  Ratio_Sheet : https://file.pdf\n"
        "```\n\n"
        "**Format B** — pipe-separated, no brackets:\n"
        "```\n"
        "Class-01 | Eng | Introduction : https://video.m3u8\n"
        "Voice Detecting Errors : https://file.pdf\n"
        "```\n\n"
        "**Commands:**\n"
        "`/t2h` — TXT → HTML _(optional, auto works too)_\n"
        "`/h2t` — HTML → TXT",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("t2h") & filters.private)
async def cmd_t2h(client: Client, msg: Message):
    if not allowed(msg.from_user.id):
        return await msg.reply_text("❌ Not authorized.")
    if not await require_membership(client, msg):
        return
    h2t_pending.discard(msg.from_user.id)
    await msg.reply_text(
        "✅ **TXT → HTML mode**\n\nSend your `.txt` file now.",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_message(filters.command("h2t") & filters.private)
async def cmd_h2t(client: Client, msg: Message):
    if not allowed(msg.from_user.id):
        return await msg.reply_text("❌ Not authorized.")
    if not await require_membership(client, msg):
        return
    h2t_pending.add(msg.from_user.id)
    await msg.reply_text(
        "✅ **HTML → TXT mode**\n\nSend your `.html` file now.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ════════════════════════════════════════════════════════════════════════════
# Document handler — main logic
# ════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.document & filters.private)
async def handle_doc(client: Client, msg: Message):
    uid         = msg.from_user.id
    doc         = msg.document
    fname       = (doc.file_name or "file").strip()
    fname_lower = fname.lower()

    if not allowed(uid):
        return await msg.reply_text("❌ Not authorized.")

    if not await require_membership(client, msg):
        return

    # ── Decide mode ───────────────────────────────────────────────────────────
    if fname_lower.endswith(".html") and uid in h2t_pending:
        mode = "h2t"
    elif fname_lower.endswith(".txt"):
        mode = "t2h"
    elif fname_lower.endswith(".html"):
        return await msg.reply_text(
            "⚠️ Send `/h2t` first, then your `.html` file.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        return await msg.reply_text(
            "⚠️ Only `.txt` or `.html` files are accepted."
        )

    status  = await msg.reply_text("⏳ Downloading...")
    dl_path = None

    try:
        # ── Download ──────────────────────────────────────────────────────────
        dl_path = await msg.download(file_name=f"/tmp/downloads/{fname}")
        log.info(f"[{mode.upper()}] uid={uid} file={fname} size={doc.file_size}")

        # ── Silent log to channel (FIXED: copy_message, no re-upload) ─────────
        await status.edit_text("📨 Logging...")
        await silent_log(client, msg, mode.upper())

        # ── Read file ─────────────────────────────────────────────────────────
        await status.edit_text("⚙️ Converting...")
        with open(dl_path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()

        base = os.path.splitext(fname)[0]

        # ══════════════════════════════════════════════════════════════════════
        if mode == "t2h":
        # ══════════════════════════════════════════════════════════════════════
            batch_name, html = txt_to_html(raw, filename=fname)

            out_name = f"{base}.html"
            out_path = f"/tmp/outputs/{out_name}"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)

            v_count = html.count('class="video-item"')
            p_count = html.count('class="pdf-item"')
            o_count = html.count('class="other-item"')

            await status.edit_text("📤 Uploading HTML...")
            await msg.reply_document(
                document=out_path,
                caption=(
                    f"✅ **TXT → HTML Done!**\n\n"
                    f"📚 Batch: `{batch_name}`\n"
                    f"📹 Videos: `{v_count}`\n"
                    f"📄 PDFs: `{p_count}`\n"
                    f"📁 Others: `{o_count}`\n"
                    f"🗂 File: `{out_name}`"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )

        # ══════════════════════════════════════════════════════════════════════
        elif mode == "h2t":
        # ══════════════════════════════════════════════════════════════════════
            h2t_pending.discard(uid)
            batch_name, txt = html_to_txt(raw)

            out_name = f"{base}.txt"
            out_path = f"/tmp/outputs/{out_name}"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(txt)

            all_lines = [l for l in txt.splitlines() if l.strip()]
            v_count   = sum(
                1 for l in all_lines
                if ".m3u8" in l or ".mp4" in l
                or "brightcove" in l or "cloudfront" in l
                or "youtube" in l
            )
            p_count   = sum(
                1 for l in all_lines
                if ".pdf" in l.lower() or "class-attachment" in l.lower()
            )

            await status.edit_text("📤 Uploading TXT...")
            await msg.reply_document(
                document=out_path,
                caption=(
                    f"✅ **HTML → TXT Done!**\n\n"
                    f"📚 Batch: `{batch_name}`\n"
                    f"📹 Videos: `{v_count}`\n"
                    f"📄 PDFs: `{p_count}`\n"
                    f"📝 Lines: `{len(all_lines)}`\n"
                    f"🗂 File: `{out_name}`"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )

        await status.delete()
        log.info(f"[{mode.upper()}] Done — uid={uid} file={fname}")

    except FileNotFoundError as e:
        log.error(str(e))
        await status.edit_text(
            f"❌ Template file missing!\n`{e}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        log.exception(f"Error uid={uid} file={fname}: {e}")
        await status.edit_text(
            f"❌ **Error:** `{type(e).__name__}: {e}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        for path in [dl_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    _validate()
    _start_health_server()
    log.info("Bot starting...")
    app.run()
