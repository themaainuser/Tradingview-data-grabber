"""The committed frontend fixtures are exactly what the backend produces today."""

from __future__ import annotations

import json

from trading_fixtures import TARGET, build


def test_the_frontend_fixtures_match_what_the_backend_produces():
    committed = json.loads(TARGET.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(build(), sort_keys=True)), "run `python tests/trading_fixtures.py` to regenerate frontend/src/lib/testing/trading-fixtures.json"


def test_every_answer_has_the_envelope_and_no_credential_in_it():
    text = json.dumps(build())
    assert "PKTRADINGKEYID" not in text and "trading-secret" not in text
    answers = {name: answer for name, answer in build().items() if name != "environments"}
    assert {"environment", "status", "message", "code", "http_status", "outcome_unknown", "client_order_id", "data", "fetched_at", "elapsed_ms"} == set(answers["account"])
    assert {a["status"] for a in answers.values()} == {"ok", "rejected", "not_found", "not_configured", "invalid_key", "upstream_error"}
    assert answers["outcome_unknown"]["outcome_unknown"] is True and answers["outcome_unknown"]["client_order_id"] == "fixture-6"
