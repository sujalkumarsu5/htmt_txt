# HTML ↔ TXT Converter Bot

A Telegram bot that converts `.txt` files to styled `.html` and vice versa.

---

## 🧩 Supported HTML → TXT Formats

`/h2t` understands these layouts automatically (no extra command needed):

| Style | Source layout |
|---|---|
| A | `subject_template.html` (folder-content / video-item / pdf-item / other-item) |
| B | tab-based `videos-tab` / `pdfs-tab` with `list-item` cards |
| C | JS `CONFIG` object with base64-encoded URLs (GS_special_2 style) |
| D | Generic fallback — any anchor with a usable `href` / `onclick` URL |
| E | CareerWill tab format (`tab-content` id=`video`/`pdf`/`other`, `card` divs) |
| **F** | **XOR + Base64 encrypted payload (Maths Special VOD style)** — the bot reproduces the page's `generateSecretKey()` logic, decrypts `encodedContent`, and re-parses the inner HTML |
| **G** | **JS `const data = [{topic, items: [{n, id, d}]}]` array (SPARTAN style)** — extracts the `${i.id}` URL template (prefers 720p) and emits one line per item in `[Topic] NAME \| Date : URL` form |
| **H** | **`subject-header` / `subject-content` layout** — used inside decrypted Style-F pages, supports both `<a class="media-title">` videos and `<span class="media-title">` PDFs whose URL is embedded in the chrome `<button window.open(...)>` |

Output is always a single line per item: `[Topic] NAME | Date : URL` (single URL, no per-resolution duplicates).

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_ID` | ✅ | Telegram API ID (number) from my.telegram.org |
| `API_HASH` | ✅ | Telegram API Hash (string) from my.telegram.org |
| `BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `LOG_CHANNEL` | ❌ | Numeric channel ID e.g. `-1001234567890` |
| `FORCE_CHANNEL` | ❌ | Numeric channel ID for force-join |
| `FORCE_INVITE_LINK` | ❌ | Invite link shown to users who haven't joined |

---

## 🔴 LOG_CHANNEL Fix (Important!)

If log channel me file send nahi ho rahi / error aa raha hai:

1. **Bot ko channel ka admin banao** — "Post Messages" permission required
2. **Numeric ID use karo** — `@username` nahi, e.g. `-1001234567890`  
   Channel ka ID pane ke liye: forward a message from channel to @userinfobot
3. **Bot ko channel mein add karo** pehle, phir admin banao

The bot now uses `copy_message` instead of re-uploading, so it's faster and more reliable.

---

## 🚀 Deploy on Render (Recommended)

1. GitHub par push karo
2. [render.com](https://render.com) par jaao → New → Web Service
3. Repository connect karo
4. Environment variables set karo (upar table dekho)
5. Deploy!

Render `render.yaml` automatically detect karega.

---

## 🐳 Deploy with Docker

```bash
docker build -t converter-bot .
docker run -d \
  -e API_ID=your_api_id \
  -e API_HASH=your_api_hash \
  -e BOT_TOKEN=your_bot_token \
  -e LOG_CHANNEL=-1001234567890 \
  converter-bot
```

---

## 🟣 Deploy on Heroku

```bash
heroku create your-bot-name
heroku config:set API_ID=... API_HASH=... BOT_TOKEN=... LOG_CHANNEL=...
git push heroku main
```

---

## 🤖 Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/help` | Format guide |
| `/t2h` | TXT → HTML mode (optional, auto-detected) |
| `/h2t` | HTML → TXT mode |

Just send a `.txt` file directly — no command needed!

---

## 📁 Project Structure

```
├── main.py              # Bot logic (entry point)
├── config.py            # Environment variable config
├── html_generator.py    # TXT → HTML conversion engine
├── html_to_txt.py       # HTML → TXT conversion engine
├── subject_template.html # HTML output template
├── requirements.txt     # Python dependencies
├── render.yaml          # Render deployment config
├── Dockerfile           # Docker deployment config
├── Procfile             # Heroku deployment config
├── heroku.yml           # Heroku Docker config
├── app.py               # Flask web server (for Procfile)
└── runtime.txt          # Python version for Heroku
```
