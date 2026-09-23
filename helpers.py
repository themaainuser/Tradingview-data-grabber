"""Backward-compatible imports for the modular protocol helpers."""

from tradingview_data.protocol import (
    construct_message,
    create_message,
    frame_payload,
    filter_raw_message,
    generate_chart_session,
    generate_quote_session,
    is_heartbeat,
    iter_frame_payloads,
    iter_frames,
    send_message,
    send_raw_message,
)


def generateSession():
    """Return a legacy quote-session identifier."""

    return generate_quote_session()


def generateChartSession():
    """Return a legacy chart-session identifier."""

    return generate_chart_session()


def prependHeader(st):
    """Frame a raw protocol payload using the legacy argument name."""

    return frame_payload(st)


def constructMessage(func, paramList):
    """Build a message body using the legacy argument names."""

    return construct_message(func, paramList)


def createMessage(func, paramList):
    """Build a framed message using the legacy argument names."""

    return create_message(func, paramList)


def sendRawMessage(ws, message):
    """Send a framed raw payload through a websocket-like object."""

    return send_raw_message(ws, message)


def sendMessage(ws, func, args):
    """Send a framed method call through a websocket-like object."""

    return send_message(ws, func, args)


__all__ = [
    "constructMessage",
    "construct_message",
    "createMessage",
    "create_message",
    "filter_raw_message",
    "generateChartSession",
    "generateSession",
    "generate_chart_session",
    "generate_quote_session",
    "is_heartbeat",
    "iter_frame_payloads",
    "iter_frames",
    "prependHeader",
    "sendMessage",
    "sendRawMessage",
    "send_message",
    "send_raw_message",
]
