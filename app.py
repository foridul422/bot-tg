import os
import sys
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

import requests
from flask import Flask, abort, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from main import (  # noqa: E402
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_SPAM_WINDOW_SECONDS,
    LAST_USER_ACTION,
    decryptor_for_file,
    decryptor_title,
    designed_message,
    fail_message,
    find_document,
    help_text,
    important_preview,
    is_npv_file,
    parse_allowed_users,
    parse_positive_int,
    requester_link,
    result_keyboard,
    run_decryptors,
    start_keyboard,
    v2ray_links_from_result,
    v2ray_links_message,
)

app = Flask(__name__)


def env_text(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or ""


def bot_token() -> str:
    token = env_text("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN missing")
    return token


def env_bool(name: str, default: bool = False) -> bool:
    value = env_text(name)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def can_send_import_links(sender: Dict[str, Any], chat: Dict[str, Any]) -> bool:
    if not env_bool("ENABLE_IMPORT_LINKS"):
        return False

    return is_allowed_private_output(sender, chat)


def can_send_sensitive_fields(sender: Dict[str, Any], chat: Dict[str, Any]) -> bool:
    if not env_bool("SHOW_SENSITIVE_FIELDS"):
        return False

    return is_allowed_private_output(sender, chat)


def is_allowed_private_output(sender: Dict[str, Any], chat: Dict[str, Any]) -> bool:
    allowed_users = parse_allowed_users(env_text("ALLOWED_USER_IDS"))
    sender_id = sender.get("id")
    if allowed_users:
        return sender_id in allowed_users

    return chat.get("type") == "private"


class TelegramClient:
    def __init__(self, token: str):
        self.api_base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"

    def call(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(f"{self.api_base}/{method}", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "",
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
            payload["allow_sending_without_reply"] = True
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.call("sendMessage", payload)

    def edit_message(self, chat_id: int, message_id: Optional[int], text: str) -> None:
        if not message_id:
            return
        try:
            self.call(
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
        except Exception as exc:
            print(f"editMessage failed: {exc}")

    def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        self.call(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": False,
            },
        )

    def get_bot_label(self) -> str:
        try:
            result = self.call("getMe", {})
            username = result.get("result", {}).get("username")
            if username:
                return f"@{username}"
        except Exception as exc:
            print(f"getMe failed: {exc}")
        return "@Decryptor2_bot"

    def get_file_bytes(self, file_id: str) -> bytes:
        file_info = self.call("getFile", {"file_id": file_id})
        file_path = file_info.get("result", {}).get("file_path")
        if not file_path:
            raise ValueError("Telegram did not return a file path.")
        response = requests.get(f"{self.file_base}/{file_path}", timeout=60)
        response.raise_for_status()
        return response.content


@app.get("/")
def health():
    return "Telegram config bot is running."


@app.get("/register")
def register_webhook():
    setup_secret = env_text("SETUP_SECRET")
    supplied_key = request.args.get("key", "")
    if setup_secret and supplied_key != setup_secret:
        abort(403)

    webhook_url = request.url_root.rstrip("/") + "/webhook"
    payload: Dict[str, Any] = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False,
    }
    secret = env_text("WEBHOOK_SECRET")
    if secret:
        payload["secret_token"] = secret
    return jsonify(TelegramClient(bot_token()).call("setWebhook", payload))


@app.post("/webhook")
def webhook():
    secret = env_text("WEBHOOK_SECRET")
    if secret and request.headers.get("x-telegram-bot-api-secret-token") != secret:
        abort(403)

    update = request.get_json(silent=True)
    if not isinstance(update, dict):
        abort(400)

    handle_update(update)
    return "ok"


def handle_callback(client: TelegramClient, callback_query: Dict[str, Any]) -> None:
    query_id = str(callback_query.get("id") or "")
    data = str(callback_query.get("data") or "")
    message = callback_query.get("message") or {}
    chat = message.get("chat") if isinstance(message, dict) else {}
    chat_id = chat.get("id") if isinstance(chat, dict) else None

    if query_id:
        client.answer_callback_query(
            query_id,
            "Supported: .dark, .ehi, .hc, .ssc" if data == "supported" else "OK",
        )

    if chat_id and data == "supported":
        client.send_message(int(chat_id), help_text(), parse_mode="HTML", reply_markup=start_keyboard())


def handle_update(update: Dict[str, Any]) -> None:
    client = TelegramClient(bot_token())

    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        handle_callback(client, callback_query)
        return

    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    sender = message.get("from") or {}
    allowed_users = parse_allowed_users(env_text("ALLOWED_USER_IDS"))
    if allowed_users and sender.get("id") not in allowed_users:
        client.send_message(int(chat_id), "Sorry, ei bot private.")
        return

    text = message.get("text") or ""
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text else ""
    if command == "/start" or command == "/help":
        client.send_message(int(chat_id), help_text(), parse_mode="HTML", reply_markup=start_keyboard())
        return
    if command == "/id":
        user_id = sender.get("id") or "unknown"
        client.send_message(int(chat_id), f"Your Telegram ID: {user_id}")
        return
    if command == "/stats":
        client.send_message(int(chat_id), "Stats feature ekhon off ache.")
        return

    document = find_document(message)
    if not document:
        client.send_message(
            int(chat_id),
            "Ekta config file upload koro.\n\nSupported: .dark, .ehi, .hc, .ssc",
            reply_markup=start_keyboard(),
        )
        return

    sender_id = sender.get("id")
    if isinstance(sender_id, int):
        spam_window = parse_positive_int(env_text("SPAM_WINDOW_SECONDS"), DEFAULT_SPAM_WINDOW_SECONDS)
        now = time.time()
        wait_for = int(spam_window - (now - LAST_USER_ACTION.get(sender_id, 0)))
        if wait_for > 0:
            client.send_message(int(chat_id), f"Please {wait_for}s wait koro, tarpor next file pathao.")
            return
        LAST_USER_ACTION[sender_id] = now

    file_name = document.get("file_name") or "telegram_config"
    file_size = int(document.get("file_size") or 0)
    max_file_size = int(env_text("MAX_FILE_SIZE", str(DEFAULT_MAX_FILE_SIZE)))
    reply_to_message_id = message.get("message_id")

    if file_size and file_size > max_file_size:
        client.send_message(
            int(chat_id),
            f"File ta beshi boro. Limit: {max_file_size // (1024 * 1024)} MB.",
            reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
        )
        return

    if is_npv_file(file_name):
        client.send_message(
            int(chat_id),
            fail_message(file_name, None, ()),
            reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
        )
        return

    detected = decryptor_for_file(file_name)
    processing = client.send_message(
        int(chat_id),
        f"Unlocking {detected['name']} config..." if detected else "Unlocking config...",
        reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
    )
    processing_message_id = processing.get("result", {}).get("message_id")

    try:
        file_bytes = client.get_file_bytes(document["file_id"])
        started_at = time.perf_counter()
        decryptor_name, result, errors, detected_name = run_decryptors(file_bytes, file_name)
        elapsed_ms = max(1, int((time.perf_counter() - started_at) * 1000))
    except Exception as exc:
        client.edit_message(int(chat_id), processing_message_id, f"File process korte parlam na: {exc}")
        return

    if not result or not decryptor_name:
        client.edit_message(int(chat_id), processing_message_id, fail_message(file_name, detected_name, errors))
        return

    preview = important_preview(
        result,
        decryptor_name,
        can_send_sensitive_fields(sender, chat),
    )
    client.send_message(
        int(chat_id),
        designed_message(
            decryptor_title(decryptor_name),
            requester_link(sender),
            client.get_bot_label(),
            elapsed_ms,
            preview,
            decryptor_name == "HTTP Injector",
        ),
        parse_mode="HTML",
        reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
        reply_markup=result_keyboard(),
    )
    if can_send_import_links(sender, chat):
        links = v2ray_links_from_result(result, file_name, decryptor_name)
        if links:
            client.send_message(
                int(chat_id),
                v2ray_links_message(links),
                parse_mode="HTML",
                reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
            )
    client.edit_message(int(chat_id), processing_message_id, f"Done | {decryptor_name} | {elapsed_ms}ms")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
