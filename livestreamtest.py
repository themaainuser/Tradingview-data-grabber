import argparse
import csv
import json
import os
from datetime import datetime
from time import sleep
from zoneinfo import ZoneInfo

from websocket import create_connection

from helpers import generateSession, generateChartSession, sendMessage, is_heartbeat, iter_frames

URL = 'wss://data.tradingview.com/socket.io/websocket'
HEADERS = json.dumps({
    'Origin': 'https://data.tradingview.com'
})
MAX_RETRIES = 5
RECV_TIMEOUT = 30
IST = ZoneInfo("Asia/Kolkata")
CSV_TIME_FORMAT = '%a %b %d %Y %H:%M:%S GMT%z'


def parse_csv_time(s):
    try:
        return int(datetime.strptime(s, CSV_TIME_FORMAT).timestamp())
    except (ValueError, TypeError):
        return None


def backoff_delay(attempts):
    return min(2 ** attempts, 30)


def safe_filename(symbol):
    return symbol.replace(":", "_").replace("/", "_")


class SymbolStream:
    """Per-symbol state: its own chart session, csv writer, and dedup state."""

    def __init__(self, symbol, csv_path):
        self.symbol = symbol
        self.chart_session = generateChartSession()
        self.csv_path = csv_path
        self.file = None
        self.writer = None
        self.last_key = None
        self.last_row_pos = None
        self.written = set()

    def open(self):
        is_new = (not os.path.exists(self.csv_path)
                  or os.path.getsize(self.csv_path) == 0)
        if not is_new:
            self._load_existing_state()
        self.file = open(self.csv_path, "a" if not is_new else "w", newline="")
        self.writer = csv.writer(self.file, delimiter=',', quotechar='"',
                                 quoting=csv.QUOTE_MINIMAL)
        if is_new:
            self.writer.writerow(['index', 'time', 'open', 'high',
                                  'low', 'close', 'volume'])
            self.file.flush()

    def _load_existing_state(self):
        """On restart, remember every timestamp already in the CSV so the new
        session's history resend is skipped and the forming candle is rewritten
        in place instead of appended as a duplicate."""
        with open(self.csv_path, "r", newline="") as f:
            pos = f.tell()
            line = f.readline()
            while line:
                next_pos = f.tell()
                row = next(csv.reader([line], delimiter=',',
                                      quotechar='"'), None)
                if row and row[0].startswith("[") and row[0].endswith("]"):
                    ts = parse_csv_time(row[1])
                    if ts is not None:
                        self.written.add(ts)
                        self.last_key = ts
                        self.last_row_pos = pos
                pos = next_pos
                line = f.readline()

    def close(self):
        if self.file:
            self.file.close()

    def write_bar(self, key, row):
        if key in self.written and key != self.last_key:
            return
        if key == self.last_key:
            self.file.seek(self.last_row_pos)  # type: ignore
            self.file.truncate()  # type: ignore
        else:
            self.last_key = key
            self.last_row_pos = self.file.tell()  # type: ignore
            self.written.add(key)
        self.writer.writerow(row)  # type: ignore
        self.file.flush()  # type: ignore


def parse_bar(bar):
    v = bar.get("v") or []
    if len(v) < 5:
        return None
    ts_epoch = int(float(v[0]))
    ts = datetime.fromtimestamp(ts_epoch, IST)
    ts_str = ts.strftime(CSV_TIME_FORMAT)
    volume = v[5] if len(v) > 5 else ""
    return ts_epoch, ["[{}]".format(bar.get("i")), ts_str, v[1], v[2], v[3], v[4], volume]


def collect_bars(text):
    """Yields (chart_session_id, key, row) so callers can route to the right symbol."""
    for frame in iter_frames(text):
        if not isinstance(frame, dict) or frame.get("m") not in ("du", "timescale_update"):
            continue
        payload = frame.get("p")
        if not isinstance(payload, list) or len(payload) < 2:
            continue
        session_id = payload[0]
        series = payload[1]
        if not isinstance(series, dict):
            continue
        for series_name in series:
            for bar in series[series_name].get("s") or []:
                parsed = parse_bar(bar)
                if parsed is not None:
                    key, row = parsed
                    yield session_id, key, row


def subscribe(ws, streams, args):
    quote_session = generateSession()
    sendMessage(ws, "set_auth_token", ["unauthorized_user_token"])
    sendMessage(ws, "quote_create_session", [quote_session])
    sendMessage(ws, "quote_set_fields", [
                quote_session, "lp", "volume", "currency_code"])

    for stream in streams.values():
        sendMessage(ws, "quote_add_symbols", [quote_session, stream.symbol])
        sendMessage(ws, "quote_fast_symbols", [quote_session, stream.symbol])

    sendMessage(ws, "quote_hibernate_all", [quote_session])

    for stream in streams.values():
        sendMessage(ws, "chart_create_session", [stream.chart_session, ""])
        payload = "={\"symbol\":\"%s\",\"adjustment\":\"splits\"}" % stream.symbol
        sendMessage(ws, "resolve_symbol", [
                    stream.chart_session, "symbol_1", payload])
        sendMessage(ws, "create_series", [
                    stream.chart_session, "s1", "s1", "symbol_1", args.timeframe, args.bars])


def build_streams(args):
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("no symbols provided")

    os.makedirs(args.output, exist_ok=True)
    streams = {}
    for symbol in symbols:
        csv_path = os.path.join(args.output, safe_filename(symbol) + ".csv")
        stream = SymbolStream(symbol, csv_path)
        streams[stream.chart_session] = stream
    return streams


def run(args):
    streams = build_streams(args)
    for stream in streams.values():
        stream.open()

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
                sleep(delay)
                continue

            attempts = 0
            try:
                subscribe(ws, streams, args)
                while True:
                    result = ws.recv()
                    if is_heartbeat(result):
                        ws.send(result)
                        continue
                    if not args.silent:
                        print(result)
                    for session_id, key, row in collect_bars(result):
                        stream = streams.get(session_id)
                        if stream is None:
                            continue
                        stream.write_bar(key, row)
            except KeyboardInterrupt:
                print("interrupted, csv(s) saved to {}".format(args.output))
                return
            except Exception as e:
                print("stream error: {}".format(e))
            finally:
                ws.close()
            delay = backoff_delay(attempts)
            print("reconnecting in {}s".format(delay))
            sleep(delay)
    finally:
        for stream in streams.values():
            stream.close()


def main():
    parser = argparse.ArgumentParser(
        description="Stream TradingView live OHLCV bars for one or more symbols to CSV, over a single websocket")
    parser.add_argument("-n", "--symbols", default="BINANCE:BTCUSDT",
                        help="comma-separated symbols, e.g. BINANCE:BTCUSDT,NSE:RELIANCE "
                             "(default: BINANCE:BTCUSDT)")
    parser.add_argument("-t", "--timeframe", default="1",
                        help="bar timeframe in minutes (default: 1)")
    # How many bars TradingView returns is capped: ~5000 for 1m,
    # less for higher timeframes (daily ~1000-2000).
    parser.add_argument("-b", "--bars", type=int, default=300,
                        help="bars requested on connect (default: 300)")
    parser.add_argument("-o", "--output", default="data",
                        help="output data folder containing one CSV per symbol "
                             "(default: data)")
    parser.add_argument("-s", "--silent", help="silent", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
