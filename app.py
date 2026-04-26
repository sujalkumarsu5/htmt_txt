"""
app.py — Minimal Flask web server

Used by Heroku / Railway via Procfile + gunicorn.
Render uses the built-in HTTP server in main.py instead.
"""

from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "Bot is running! ✅", 200


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
