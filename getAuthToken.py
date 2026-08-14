import logging
import re
from websocket import create_connection
import os
import requests

from helpers import sendMessage

logger = logging.getLogger(__name__)

HEADERS = {'Connection': 'upgrade',
           'Host': 'data.tradingview.com',
           'Referer': 'https://www.tradingview.com',
           'Origin': 'https://data.tradingview.com',
           'Cache-Control': 'no-cache',
           'Upgrade': 'websocket',
           'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
           'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36 Edg/83.0.478.56',
           'Pragma': 'no-cache', }


def get_auth_token():
    sign_in_url = 'https://www.tradingview.com/accounts/signin/'
    username = os.getenv("TV_USERNAME")
    password = os.getenv("TV_PASSWORD")
    data = {"username": username, "password": password, "remember": "on"}
    headers = {
        'Referer': 'https://www.tradingview.com'
    }
    with requests.Session() as session:

        response = session.post(url=sign_in_url, data=data,
                                headers=headers, timeout=20)
        response.raise_for_status()

        result = response.json()

    try:
        return result["user"]["auth_token"]

    except KeyError:
        raise RuntimeError(
            f"Unexpected login response: {result}"
        )


def main():
    ws = create_connection(
        'wss://data.tradingview.com/socket.io/websocket?from=chart/Xyour_chartXX/&date=XXXX_XX_XX-XX_XX', HEADERS)

    auth_token = get_auth_token()

    sendMessage(ws, "set_auth_token", [auth_token])

    heartbeat = re.compile(r"^~m~\d+~m~~h~\d+$")

    try:
        while True:
            message = ws.recv()

            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="ignore",)

            if isinstance(message, str) and heartbeat.match(message):
                ws.send(message)
                continue

            logger.info(message)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    except Exception:
        logger.exception("WebSocket failure")

    finally:
        ws.close()


if __name__ == "__main__":
    main()
