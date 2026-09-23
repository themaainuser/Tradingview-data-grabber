"""TradingView websocket framing and session helpers.

The socket protocol sends one or more ``~m~<length>~m~<payload>`` frames in a
websocket message.  Keeping that parsing here avoids every feature having its
own subtly different implementation.
"""

from __future__ import annotations

import json
import re
import secrets
import string
from collections.abc import Iterator, Sequence
from typing import Any

FRAME_MARKER = "~m~"
_FRAME_MARKER_BYTES = FRAME_MARKER.encode("ascii")
ANONYMOUS_TOKEN = "unauthorized_user_token"
DEFAULT_ENDPOINT = "wss://data.tradingview.com/socket.io/websocket"
DEFAULT_ORIGIN = "https://data.tradingview.com"

_HEARTBEAT_RE = re.compile(r"^~m~\d+~m~~h~\d+$")


def as_text(value: str | bytes) -> str:
    """Return a decoded websocket message or raise for an unsupported value."""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    raise TypeError("websocket messages must be str or bytes")


def is_heartbeat(value: str | bytes) -> bool:
    """Whether *value* is a TradingView heartbeat frame."""

    try:
        return _HEARTBEAT_RE.fullmatch(as_text(value)) is not None
    except TypeError:
        return False


def frame_payload(payload: str) -> str:
    """Wrap a protocol payload in a TradingView length-prefixed frame."""

    return f"{FRAME_MARKER}{len(payload.encode('utf-8'))}{FRAME_MARKER}{payload}"


def construct_message(method: str, params: Sequence[Any]) -> str:
    """Build the JSON payload for a protocol method call."""

    return json.dumps({"m": method, "p": list(params)}, separators=(",", ":"))


def create_message(method: str, params: Sequence[Any]) -> str:
    """Build a complete framed protocol method call."""

    return frame_payload(construct_message(method, params))


def send_raw_message(websocket: Any, message: str) -> None:
    """Send a raw JSON protocol payload through a websocket-like object."""

    websocket.send(frame_payload(message))


def send_message(websocket: Any, method: str, params: Sequence[Any]) -> None:
    """Serialize and send a protocol method call."""

    websocket.send(create_message(method, params))


def _as_bytes(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError("websocket messages must be str or bytes")


def _next_frame_start(value: bytes, position: int) -> int:
    """Find a syntactically valid frame header without matching payload text."""

    candidate = value.find(_FRAME_MARKER_BYTES, position)
    while candidate >= 0:
        length_start = candidate + len(_FRAME_MARKER_BYTES)
        length_end = value.find(_FRAME_MARKER_BYTES, length_start)
        if length_end >= 0 and value[length_start:length_end].isdigit():
            return candidate
        candidate = value.find(_FRAME_MARKER_BYTES, candidate + len(_FRAME_MARKER_BYTES))
    return -1


def _decode_payload(value: bytes) -> str | None:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _is_json_payload(value: str | None) -> bool:
    if value is None:
        return False
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return False
    return True


def iter_frame_payloads(value: str | bytes) -> Iterator[str]:
    """Yield UTF-8 payloads from a websocket message.

    Frame lengths are UTF-8 byte counts, so parsing happens on bytes rather
    than Python character offsets. A valid JSON remainder with an inaccurate
    final length is accepted for compatibility with historical captures.
    """

    raw = _as_bytes(value)
    position = 0

    while position < len(raw):
        frame_start = _next_frame_start(raw, position)
        if frame_start < 0:
            return
        length_start = frame_start + len(_FRAME_MARKER_BYTES)
        length_end = raw.find(_FRAME_MARKER_BYTES, length_start)
        declared = int(raw[length_start:length_end])
        payload_start = length_end + len(_FRAME_MARKER_BYTES)
        payload_end = payload_start + declared

        if payload_end <= len(raw):
            payload = _decode_payload(raw[payload_start:payload_end])
            if payload is not None and (payload.startswith("~h~") or _is_json_payload(payload)):
                yield payload
                position = payload_end
                continue

            next_frame = _next_frame_start(raw, payload_start)
            if next_frame < 0:
                position = payload_end
                continue
            fallback = _decode_payload(raw[payload_start:next_frame])
            if fallback is not None and (fallback.startswith("~h~") or _is_json_payload(fallback)):
                yield fallback
            position = next_frame
            continue

        # Some old captures contain an inaccurate final length. Only consume
        # the remainder if it independently decodes to JSON or a heartbeat.
        next_frame = _next_frame_start(raw, payload_start)
        remainder_end = next_frame if next_frame >= 0 else len(raw)
        payload = _decode_payload(raw[payload_start:remainder_end])
        if payload is not None and (payload.startswith("~h~") or _is_json_payload(payload)):
            yield payload
        if next_frame < 0:
            return
        position = next_frame


def iter_frames(value: str | bytes) -> Iterator[dict[str, Any]]:
    """Yield well-formed JSON protocol frames from a websocket message."""

    for payload in iter_frame_payloads(value):
        try:
            frame = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if isinstance(frame, dict):
            yield frame


def filter_raw_message(value: str | bytes) -> tuple[str | None, str | None]:
    """Return the first protocol method name and compact payload JSON."""

    for frame in iter_frames(value):
        method = frame.get("m")
        if not isinstance(method, str):
            continue
        return method, json.dumps(frame.get("p", []), separators=(",", ":"))
    return None, None


def generate_session(prefix: str) -> str:
    """Generate a cryptographically random TradingView session identifier."""

    if not re.fullmatch(r"[a-z_]+", prefix):
        raise ValueError("session prefixes may contain only lowercase letters and underscores")
    suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(12))
    return f"{prefix}{suffix}"


def generate_quote_session() -> str:
    return generate_session("qs_")


def generate_chart_session() -> str:
    return generate_session("cs_")


# The original project exposed camelCase helper names.  Keep them as aliases
# so downstream scripts can move to the package incrementally.
generateSession = generate_quote_session
generateChartSession = generate_chart_session
prependHeader = frame_payload
constructMessage = construct_message
createMessage = create_message
sendRawMessage = send_raw_message
sendMessage = send_message
