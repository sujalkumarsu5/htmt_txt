"""
config.py — Bot configuration

All values are read from environment variables.
Set these in Render / Heroku / your .env file.

Required:
  API_ID        — Telegram API ID (number)
  API_HASH      — Telegram API Hash (string)
  BOT_TOKEN     — Bot Token from @BotFather

Optional:
  LOG_CHANNEL   — Numeric channel ID e.g. -1001234567890
                  Bot MUST be admin with "Post Messages" permission!
  FORCE_CHANNEL — Numeric channel ID for force-join gate
  FORCE_INVITE_LINK — Invite link shown to non-members
"""

import os


def _int(key: str, default: int = 0) -> int:
    """Safely parse env var to int — strips whitespace/quotes/newlines."""
    raw = os.environ.get(key, "").strip().strip('"').strip("'").strip()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


API_ID    = _int("API_ID")
API_HASH  = os.environ.get("API_HASH", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# ── Log channel ───────────────────────────────────────────────────────────────
# Numeric ID of the log channel (e.g. -1001234567890)
# Bot MUST be admin with "Post Messages" permission in this channel!
LOG_CHANNEL = _int("LOG_CHANNEL")

# ── Force-join channel ────────────────────────────────────────────────────────
# Users must be member of this channel to use the bot.
# Set FORCE_CHANNEL=0 to disable the gate entirely.
_DEFAULT_FORCE_CHANNEL     = 0          # 0 = disabled (change to your channel ID)
_DEFAULT_FORCE_INVITE_LINK = "https://t.me/your_channel"

FORCE_CHANNEL     = _int("FORCE_CHANNEL") or _DEFAULT_FORCE_CHANNEL
FORCE_INVITE_LINK = (
    os.environ.get("FORCE_INVITE_LINK", "").strip()
    or _DEFAULT_FORCE_INVITE_LINK
)

# ── Allowed users ─────────────────────────────────────────────────────────────
# Leave [] to allow everyone (force-join check still applies if FORCE_CHANNEL set)
ALLOWED_USERS: list[int] = []
