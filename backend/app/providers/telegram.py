"""The Telegram Bot API, only the calls Field Watch uses (docs/13-notifications.md#telegram)."""

import json
import time

import httpx

API = "https://api.telegram.org/bot{token}/{method}"
# The longest wait for a "slow down" before giving up on that message; the next run retries.
MAX_RETRY_AFTER_S = 30

# Rows of inline buttons, each a list of {"text": ..., "url" or "callback_data": ...}.
Buttons = list[list[dict]]


class TelegramError(Exception):
    """Telegram refused a call; `description` is its reason."""


class TelegramBlocked(TelegramError):
    """The user blocked the bot or deleted the chat (HTTP 403): nothing can reach that chat."""


class Telegram:
    def __init__(self, client: httpx.Client, token: str):
        self.client = client
        self.token = token

    def _call(self, method: str, files: dict | None = None, **params) -> dict | list | bool:
        # The token is part of the address: errors never carry the address, only the reason.
        url = API.format(token=self.token, method=method)
        for attempt in (1, 2):
            if files:
                data = {
                    k: json.dumps(v) if isinstance(v, dict | list) else v for k, v in params.items()
                }
                response = self.client.post(url, data=data, files=files, timeout=30)
            else:
                response = self.client.post(url, json=params, timeout=30)
            body = response.json()
            if body.get("ok"):
                return body["result"]
            retry_after = (body.get("parameters") or {}).get("retry_after")
            if response.status_code == 429 and retry_after and attempt == 1:
                if retry_after > MAX_RETRY_AFTER_S:
                    break
                time.sleep(retry_after)
                continue
            break
        description = body.get("description", f"HTTP {response.status_code}")
        if response.status_code == 403:
            raise TelegramBlocked(description)
        raise TelegramError(description)

    def username(self) -> str:
        return self._call("getMe")["username"]

    def updates(self, offset: int | None) -> list[dict]:
        """Messages and button taps since `offset`; at once, without waiting for new ones."""
        params = {"timeout": 0, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", **params)

    def send_text(
        self,
        chat_id: int,
        text: str,
        buttons: Buttons | None = None,
        silent: bool = False,
        keyboard: dict | None = None,
        remove_keyboard: bool = False,
    ) -> dict:
        """`buttons` go under the message; `keyboard` replaces the keyboard below the chat, and
        `remove_keyboard` takes it away. A message carries one of the three."""
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
            "disable_notification": silent,
        }
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        elif keyboard:
            params["reply_markup"] = keyboard
        elif remove_keyboard:
            params["reply_markup"] = {"remove_keyboard": True}
        return self._call("sendMessage", **params)

    def edit_text(self, chat_id: int, message_id: int, text: str, buttons: Buttons) -> None:
        """Changes a message in place, so moving between views does not fill the chat."""
        try:
            self._call(
                "editMessageText",
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                link_preview_options={"is_disabled": True},
                reply_markup={"inline_keyboard": buttons},
            )
        except TelegramError as exc:
            # A tap that would show what is already there.
            if "message is not modified" not in str(exc):
                raise

    def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        caption: str,
        buttons: Buttons | None = None,
        silent: bool = False,
    ) -> dict:
        params = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
            "disable_notification": silent,
        }
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        return self._call("sendPhoto", files={"photo": ("area.png", photo, "image/png")}, **params)

    def chat_action(self, chat_id: int, action: str) -> None:
        """What the chat shows while a message is being prepared, e.g. "upload_photo"."""
        self._call("sendChatAction", chat_id=chat_id, action=action)

    def answer_button(self, callback_id: str, text: str) -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def set_buttons(self, chat_id: int, message_id: int, buttons: Buttons) -> None:
        self._call(
            "editMessageReplyMarkup",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": buttons},
        )

    def set_profile(
        self, language: str, commands: list[dict], description: str, short_description: str
    ) -> None:
        """The bot's menu of commands and its texts before Start and in its profile, for users
        whose Telegram is in `language`; "" sets the default for every other language."""
        scope = {"language_code": language} if language else {}
        self._call("setMyCommands", commands=commands, **scope)
        self._call("setMyDescription", description=description, **scope)
        self._call("setMyShortDescription", short_description=short_description, **scope)

    def show_commands_menu(self) -> None:
        self._call("setChatMenuButton", menu_button={"type": "commands"})
