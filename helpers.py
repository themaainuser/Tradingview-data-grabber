import json
import random
import string
import re

_FRAME_PREFIX_RE = re.compile(r"~m~\d+~m~")
_HEARTBEAT_RE = re.compile(r"^~m~\d+~m~~h~\d+$")


def iter_frames(text):
    for frame in _FRAME_PREFIX_RE.split(text):
        if not frame:
            continue
        try:
            yield json.loads(frame)
        except ValueError:
            continue


def is_heartbeat(text):
    return _HEARTBEAT_RE.match(text) is not None


def filter_raw_message(text):
    for message in iter_frames(text):
        if not isinstance(message, dict) or "m" not in message:
            continue
        return message["m"], json.dumps(message["p"], separators=(",", ":"))
    return None, None


def generateSession():
    stringLength = 12
    letters = string.ascii_lowercase
    random_string = ''.join(random.choice(letters)
                            for i in range(stringLength))
    return "qs_" + random_string


def generateChartSession():
    stringLength = 12
    letters = string.ascii_lowercase
    random_string = ''.join(random.choice(letters)
                            for i in range(stringLength))
    return "cs_" + random_string


def prependHeader(st):
    return "~m~" + str(len(st)) + "~m~" + st


def constructMessage(func, paramList):
    return json.dumps({
        "m": func,
        "p": paramList
    }, separators=(',', ':'))


def createMessage(func, paramList):
    return prependHeader(constructMessage(func, paramList))


def sendRawMessage(ws, message):
    ws.send(prependHeader(message))


def sendMessage(ws, func, args):
    ws.send(createMessage(func, args))
