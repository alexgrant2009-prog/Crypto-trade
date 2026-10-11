"""Send alerts to the terminal and, if configured, to Telegram (free)."""
import os

import requests


def send(text):
    print(text, flush=True)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=10)
    except requests.RequestException as exc:
        print(f"[telegram error] {exc}", flush=True)
