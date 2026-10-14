"""The Telegram Bot API, only the calls Field Watch uses (docs/13-notifications.md#telegram)."""

import json

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    """Telegram refused a call; `description` is its reason."""


class Telegram:
    def __init__(self, client: httpx.Client, token: str):
        self.client = client
        self.token = token

    def _call(self, method: str, files: dict | None = None, **params) -> dict | list | bool:
        # The token is part of the address: errors never carry the address, only the reason.
        url = API.format(token=self.token, method=method)
        if files:
            data = {
                k: json.dumps(v) if isinstance(v, dict | list) else v for k, v in params.items()
            }
            response = self.client.post(url, data=data, files=files, timeout=30)
        else:
            response = self.client.post(url, json=params, timeout=30)
        body = response.json()
        if not body.get("ok"):
            raise TelegramError(body.get("description", f"HTTP {response.status_code}"))
        return body["result"]

    def username(self) -> str:
        return self._call("getMe")["username"]

    def updates(self, offset: int | None) -> list[dict]:
        """Messages and button taps since `offset`; at once, without waiting for new ones."""
        params = {"timeout": 0, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)

    def send_text(self, chat_id: int, text: str, buttons: list[dict] | None = None) -> dict:
        params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": [buttons]}
        return self._call("sendMessage", **params)

    def send_photo(
        self, chat_id: int, photo: bytes, caption: str, buttons: list[dict] | None = None
    ) -> dict:
        params = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": [buttons]}
        return self._call("sendPhoto", files={"photo": ("area.png", photo, "image/png")}, **params)

    def answer_button(self, callback_id: str, text: str) -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def set_buttons(self, chat_id: int, message_id: int, buttons: list[dict]) -> None:
        self._call(
            "editMessageReplyMarkup",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": [buttons]},
        )
