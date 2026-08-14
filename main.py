from websocket import create_connection
import json
import re
import time
import argparse

from helpers import generateSession, generateChartSession, sendMessage, is_heartbeat

URL = 'wss://data.tradingview.com/socket.io/websocket'
MAX_RETRIES = 5
RECV_TIMEOUT = 30

HEADERS = json.dumps({
    'Origin': 'https://data.tradingview.com'
})

QUOTE_FIELDS = ["ch", "chp", "current_session", "description", "local_description", "language", "exchange", "fractional", "is_tradable", "lp", "lp_time", "minmov",
                "minmove2", "original_name", "pricescale", "pro_name", "short_name", "type", "update_mode", "volume", "currency_code", "rchp", "rtc", "bid", "ask", "bid_size", "ask_size"]


def backoff_delay(attempts):
    return min(2 ** attempts, 30)


def resolve_symbol_payload(symbol):
    return "=" + json.dumps({"symbol": symbol, "adjustment": "splits", "session": "extended"}, separators=(",", ":"))


def subscribe(ws, symbol, silent):
    session = generateSession()
    chart_session = generateChartSession()
    if not silent:
        print("session generated {}".format(session))
        print("chart_session generated {}".format(chart_session))

    sendMessage(ws, "set_auth_token", ["unauthorized_user_token"])
    sendMessage(ws, "chart_create_session", [chart_session, ""])
    sendMessage(ws, "quote_create_session", [session])
    sendMessage(ws, "quote_set_fields", [session] + QUOTE_FIELDS)
    sendMessage(ws, "quote_add_symbols", [session, symbol])
    sendMessage(ws, "quote_fast_symbols", [session, symbol])
    sendMessage(ws, "resolve_symbol", [
                chart_session, "symbol_1", resolve_symbol_payload(symbol)])
    if not silent:
        sendMessage(ws, "create_series", [
                    chart_session, "s1", "s1", "symbol_1", "1", 5000])


def run(symbol, silent, output, exitoninput):
    out = open(output, "a") if output else None
    attempts = 0
    try:
        while True:
            if attempts >= MAX_RETRIES:
                print("giving up after {} failed attempts".format(MAX_RETRIES))
                return
            attempts += 1
            try:
                ws = create_connection(
                    URL, headers=HEADERS, timeout=RECV_TIMEOUT)
            except Exception as e:
                delay = backoff_delay(attempts)
                print("connection failed: {}; retrying in {}s".format(e, delay))
                time.sleep(delay)
                continue

            attempts = 0
            done = False
            try:
                subscribe(ws, symbol, silent)
                while True:
                    result = ws.recv()
                    if is_heartbeat(result):
                        ws.send(result)
                        continue
                    if not silent:
                        print(result)
                    if silent:
                        match = re.search(
                            r'"lp":(.*?),', result)  # type: ignore
                        if match is not None:
                            print(match.group(1))
                            if exitoninput:
                                done = True
                                break
                    if out is not None:
                        out.write(result)  # type: ignore
                        out.flush()
            except KeyboardInterrupt:
                print("interrupted")
                return
            except Exception as e:
                print("stream error: {}".format(e))
            finally:
                ws.close()
            if done:
                return
            delay = backoff_delay(attempts)
            print("reconnecting in {}s".format(delay))
            time.sleep(delay)
    finally:
        if out is not None:
            out.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--symbol", help="symbol", required=True)
    parser.add_argument("-s", "--silent", help="silent", action="store_true")
    parser.add_argument("-o", "--output", help="output", required=False)
    parser.add_argument(
        "-q", "--quit", help="quit on first response", action="store_true")
    args = parser.parse_args()
    run(args.symbol, args.silent, args.output, args.quit)


if __name__ == "__main__":
    main()
