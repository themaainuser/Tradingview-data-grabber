"""Fear & Greed: parsing, bands, comparison readings, caching and the HTTP fetch. Network-free."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest
import requests

from tradingview_data import sentiment
from tradingview_data.sentiment import (
    BANDS,
    FearGreedService,
    SentimentUnavailable,
    Snapshot,
    band_for,
    build_response,
    compute_snapshots,
    fetch_chart,
    parse_chart,
)

DAY = 86_400


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Any accidental call to the real CoinMarketCap fails the test loudly."""

    def refuse(*args, **kwargs):
        raise AssertionError("test attempted a real network request")

    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)


def utc(year, month, day, hour=0, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp())


def row(timestamp, score, price="100.5", volume="2000000.25"):
    """One ``dataList`` row in the shape CoinMarketCap returns (strings for time, price, volume)."""

    name = band_for(score).label if 0 <= score <= 100 else "invalid"
    return {"score": score, "name": name, "timestamp": str(timestamp), "btcPrice": price, "btcVolume": volume}


def payload(rows, *, error_code="0", message="SUCCESS"):
    return {
        "data": {"dataList": rows, "dialConfig": [], "historicalValues": {}},
        "status": {"timestamp": "2026-01-01T00:00:00Z", "error_code": error_code, "error_message": message},
    }


def daily(start, scores, **kwargs):
    return [row(start + i * DAY, score, **kwargs) for i, score in enumerate(scores)]


# --- bands --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "key"),
    [(0, "extreme_fear"), (19, "extreme_fear"), (20, "fear"), (39, "fear"), (40, "neutral"), (59, "neutral"),
     (60, "greed"), (79, "greed"), (80, "extreme_greed"), (100, "extreme_greed")],
)
def test_band_boundaries_include_the_lower_bound(score, key):
    assert band_for(score).key == key


@pytest.mark.parametrize("score", [-1, 101, 1000])
def test_band_for_rejects_scores_outside_the_scale(score):
    with pytest.raises(ValueError):
        band_for(score)


def test_bands_tile_the_scale_without_gaps_or_overlap():
    assert BANDS[0].start == 0 and BANDS[-1].end == 100
    assert all(a.end == b.start for a, b in zip(BANDS, BANDS[1:]))


# --- parsing ------------------------------------------------------------------------------------


def test_parse_returns_sorted_columns_and_converts_strings():
    start = utc(2026, 1, 1)
    series = parse_chart(payload([row(start + DAY, 61, "102.5", "9"), row(start, 40, "100", "8")]))
    assert series.time == (start, start + DAY)
    assert series.score == (40, 61)
    assert series.btc_price == (100.0, 102.5)
    assert series.btc_volume == (8.0, 9.0)
    assert series.dropped_rows == 0


def test_parse_drops_and_counts_unusable_rows():
    start = utc(2026, 1, 1)
    rows = [
        row(start, 50),
        row(start + DAY, 101),  # above the scale
        row(start + 2 * DAY, -3),
        {"score": 55, "timestamp": "abc"},  # unreadable time
        {"score": "n/a", "timestamp": str(start + 3 * DAY)},
        {"score": 55.5, "timestamp": str(start + 4 * DAY)},  # not a whole number
        {"timestamp": str(start + 5 * DAY)},  # missing score
        "garbage",
        row(start + 6 * DAY, 70),
    ]
    series = parse_chart(payload(rows))
    assert series.score == (50, 70)
    assert series.dropped_rows == 7


def test_parse_keeps_a_reading_without_price_and_volume_as_none():
    series = parse_chart(payload([row(utc(2026, 1, 1), 50, price=None, volume="")]))
    assert series.btc_price == (None,)
    assert series.btc_volume == (None,)


def test_parse_keeps_the_last_reading_for_a_repeated_timestamp():
    stamp = utc(2026, 1, 1)
    series = parse_chart(payload([row(stamp, 30), row(stamp, 35)]))
    assert series.score == (35,)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        (None, "unexpected response"),
        ([], "unexpected response"),
        ({"data": {}}, "no data list"),
        ({"data": {"dataList": "x"}}, "no data list"),
        (payload([]), "no usable"),
        (payload([row(utc(2026, 1, 1), 500)]), "no usable"),
    ],
)
def test_parse_rejects_unusable_payloads(body, fragment):
    with pytest.raises(SentimentUnavailable, match=fragment):
        parse_chart(body)


def test_parse_reports_an_upstream_error_delivered_with_http_200():
    # The real service answers HTTP 200 with a non-zero status code in the body when it is overloaded.
    with pytest.raises(SentimentUnavailable, match="The system is busy"):
        parse_chart(payload([], error_code="500", message="The system is busy, please try again later!"))


# --- comparison readings ------------------------------------------------------------------------


def series_from(start, scores, live_offset=None):
    rows = daily(start, scores)
    if live_offset is not None:  # a live reading later the same day as the final daily point
        rows[-1] = row(start + (len(scores) - 1) * DAY + live_offset, scores[-1])
    return parse_chart(payload(rows))


def test_snapshots_pick_the_reading_for_each_calendar_day():
    start = utc(2026, 1, 1)
    scores = list(range(10, 10 + 60))  # 60 days, strictly increasing so each day is identifiable
    series = series_from(start, scores, live_offset=6 * 3600 + 8 * 60)
    today = len(scores) - 1
    snaps = compute_snapshots(series)
    assert snaps["yesterday"]["score"] == scores[today - 1]
    assert snaps["week_ago"]["score"] == scores[today - 7]
    assert snaps["month_ago"]["score"] == scores[31]  # Jan 1 + 59 days = Mar 1; one calendar month back = Feb 1 (index 31)
    assert snaps["year_high"]["score"] == scores[-1] and snaps["year_low"]["score"] == scores[0]
    assert snaps["yesterday"]["label"] == band_for(scores[today - 1]).label
    assert snaps["yesterday"]["band"] == band_for(scores[today - 1]).key


def test_a_missing_day_is_none_rather_than_estimated():
    start = utc(2026, 1, 1)
    rows = daily(start, [50] * 20)
    del rows[12]  # no reading for the day 7 days before the latest (index 19 - 7)
    snaps = compute_snapshots(parse_chart(payload(rows)))
    assert snaps["week_ago"] is None
    assert snaps["yesterday"] is not None


def test_short_history_has_no_month_ago_but_still_has_year_extremes():
    snaps = compute_snapshots(series_from(utc(2026, 1, 1), [20, 30, 40]))
    assert snaps["month_ago"] is None and snaps["week_ago"] is None
    assert snaps["year_high"]["score"] == 40 and snaps["year_low"]["score"] == 20


def test_month_ago_clamps_to_the_end_of_a_shorter_month():
    # 2025-03-31 minus one month is 2025-02-28, which exists in the series.
    start = utc(2025, 2, 1)
    scores = list(range(1, 62))  # Feb 1 .. Apr 2
    series = series_from(start, scores)
    end_index = (datetime(2025, 3, 31, tzinfo=timezone.utc) - datetime(2025, 2, 1, tzinfo=timezone.utc)).days
    trimmed = parse_chart(payload(daily(start, scores[: end_index + 1])))
    assert compute_snapshots(trimmed)["month_ago"]["time"] == utc(2025, 2, 28)
    assert compute_snapshots(series)["month_ago"]["time"] == utc(2025, 3, 2)


def test_year_extremes_only_look_at_the_trailing_365_days_and_prefer_the_latest_tie():
    start = utc(2024, 1, 1)
    scores = [99] + [50] * 500  # an old extreme high, then a flat year
    scores[400] = 10
    scores[450] = 10
    snaps = compute_snapshots(series_from(start, scores))
    assert snaps["year_high"]["score"] == 50  # the 99 is more than a year old
    assert snaps["year_low"]["score"] == 10
    assert snaps["year_low"]["time"] == start + 450 * DAY  # latest occurrence


# --- response -----------------------------------------------------------------------------------


def test_response_contract_and_days_window():
    start = utc(2026, 1, 1)
    series = series_from(start, list(range(20, 80)))
    body = build_response(Snapshot(series, fetched_at=1234.9), days=10)
    assert sorted(body) == ["bands", "current", "fetched_at", "points", "snapshots", "source", "stale", "stale_reason", "total_points"]
    assert body["fetched_at"] == 1234 and body["stale"] is False and body["stale_reason"] is None
    assert body["total_points"] == 60
    assert len(body["points"]["time"]) == 11  # the last 10 days plus the day at the cutoff
    assert set(body["points"]) == {"time", "score", "btc_price", "btc_volume"}
    assert len({len(v) for v in body["points"].values()}) == 1
    assert body["current"] == {"score": 79, "label": "Greed", "band": "greed", "time": start + 59 * DAY}
    assert [b["key"] for b in body["bands"]] == ["extreme_fear", "fear", "neutral", "greed", "extreme_greed"]
    assert body["bands"][0]["from"] == 0 and body["bands"][-1]["to"] == 100
    assert body["source"]["documented"] is False and body["source"]["name"] == "CoinMarketCap"
    assert len(build_response(Snapshot(series, 0.0))["points"]["time"]) == 60


def test_a_days_window_shorter_than_the_spacing_still_returns_the_current_reading():
    body = build_response(Snapshot(series_from(utc(2026, 1, 1), [40, 50, 60]), 0.0), days=1)
    assert body["points"]["score"][-1] == 60


# --- service: caching, staleness, back-off -----------------------------------------------------


class Clock:
    def __init__(self, now=1_000.0):
        self.now = now

    def __call__(self):
        return self.now


class Fetcher:
    """Scripted upstream: each entry is a payload to return or an exception to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        item = self.script[min(self.calls, len(self.script)) - 1]
        if isinstance(item, Exception):
            raise item
        return item


GOOD = payload(daily(utc(2026, 1, 1), [30, 40, 50]))


def test_service_asks_upstream_once_per_ttl():
    clock, fetch = Clock(), Fetcher(GOOD)
    service = FearGreedService(fetch, ttl_seconds=600, clock=clock)
    first = service.get()
    clock.now += 599
    assert service.get().series is first.series and fetch.calls == 1
    clock.now += 2
    service.get()
    assert fetch.calls == 2
    assert first.stale is False and first.fetched_at == 1_000.0


def test_service_serves_stale_data_when_a_refresh_fails_and_flags_it():
    clock = Clock()
    fetch = Fetcher(GOOD, SentimentUnavailable("CoinMarketCap did not respond in time."))
    service = FearGreedService(fetch, ttl_seconds=600, retry_seconds=60, clock=clock)
    good = service.get()
    clock.now += 700
    stale = service.get()
    assert stale.stale is True and stale.stale_reason == "CoinMarketCap did not respond in time."
    assert stale.series is good.series and stale.fetched_at == good.fetched_at
    assert build_response(stale)["stale"] is True


def test_service_backs_off_after_a_failure_then_recovers():
    clock = Clock()
    fetch = Fetcher(SentimentUnavailable("down"), SentimentUnavailable("down"), GOOD)
    service = FearGreedService(fetch, ttl_seconds=600, retry_seconds=60, clock=clock)
    for _ in range(3):
        with pytest.raises(SentimentUnavailable, match="down"):
            service.get()
    assert fetch.calls == 1  # the two follow-ups were answered from the recorded failure
    clock.now += 61
    with pytest.raises(SentimentUnavailable):
        service.get()
    assert fetch.calls == 2
    clock.now += 61
    assert service.get().stale is False and fetch.calls == 3


def test_a_malformed_upstream_body_is_a_failure_not_data():
    service = FearGreedService(Fetcher({"data": {"dataList": []}}), clock=Clock())
    with pytest.raises(SentimentUnavailable, match="no usable"):
        service.get()


def test_concurrent_requests_share_one_upstream_call():
    calls = []
    release = threading.Event()

    def slow():
        calls.append(1)
        release.wait(2)
        return GOOD

    service = FearGreedService(slow, clock=time.time)
    results = []
    threads = [threading.Thread(target=lambda: results.append(service.get())) for _ in range(8)]
    for thread in threads:
        thread.start()
    time.sleep(0.2)
    release.set()
    for thread in threads:
        thread.join(5)
    assert len(results) == 8 and len(calls) == 1
    assert len({id(r.series) for r in results}) == 1


# --- the HTTP fetch -----------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status=200, body=None, content=b"{}"):
        self.status_code = status
        self._body = body
        self.content = content

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_fetch_sends_an_honest_keyless_request_with_timeouts():
    seen = {}

    def get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(body=GOOD)

    assert fetch_chart(now=2_000_000_000, get=get) is GOOD
    assert seen["url"] == sentiment.ENDPOINT
    assert seen["params"] == {"start": 1, "end": 2_000_000_000 + DAY}
    assert seen["timeout"] == (5, 15)
    headers = {k.lower(): v for k, v in seen["headers"].items()}
    assert headers["user-agent"].startswith("tradingview-data-grabber/")
    assert "mozilla" not in headers["user-agent"].lower()  # no pretending to be a browser
    assert not {"authorization", "x-cmc_pro_api_key", "cookie"} & set(headers)  # no credentials of any kind


@pytest.mark.parametrize(
    ("failure", "fragment"),
    [
        (requests.Timeout("slow"), "did not respond in time"),
        (requests.ConnectionError("dns"), "Could not reach CoinMarketCap"),
        (requests.RequestException("other"), "Could not reach CoinMarketCap"),
    ],
)
def test_fetch_maps_transport_errors_to_friendly_messages(failure, fragment):
    def get(*args, **kwargs):
        raise failure

    with pytest.raises(SentimentUnavailable, match=fragment) as caught:
        fetch_chart(get=get)
    assert "dns" not in str(caught.value) and "slow" not in str(caught.value)  # no internals leak to users


@pytest.mark.parametrize("status", [403, 404, 429, 500, 503])
def test_fetch_reports_a_non_200_status(status):
    with pytest.raises(SentimentUnavailable, match=f"HTTP {status}"):
        fetch_chart(get=lambda *a, **k: FakeResponse(status=status))


def test_fetch_rejects_unreadable_and_oversized_responses():
    with pytest.raises(SentimentUnavailable, match="unreadable"):
        fetch_chart(get=lambda *a, **k: FakeResponse(body=ValueError("not json")))
    huge = b"x" * (sentiment.MAX_RESPONSE_BYTES + 1)
    with pytest.raises(SentimentUnavailable, match="unexpectedly large"):
        fetch_chart(get=lambda *a, **k: FakeResponse(body=GOOD, content=huge))


def test_the_default_service_fetches_through_requests_get(monkeypatch):
    captured = []

    def fake_get(url, **kwargs):
        captured.append(url)
        return FakeResponse(body=GOOD)

    monkeypatch.setattr(requests, "get", fake_get)
    service = FearGreedService()
    assert service.get().series.score == (30, 40, 50)
    assert captured == [sentiment.ENDPOINT]
