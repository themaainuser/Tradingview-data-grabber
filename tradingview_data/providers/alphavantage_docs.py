"""Builds the Alpha Vantage endpoint catalog from its public documentation page.

``python -m tradingview_data.providers.alphavantage_docs`` downloads
https://www.alphavantage.co/documentation/ and rewrites ``alphavantage_catalog.json`` next to this
file. The catalog is committed so the app never scrapes at runtime; rerun this when Alpha Vantage
adds or changes endpoints. Only the standard library is used.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import requests

DOCS_URL = "https://www.alphavantage.co/documentation/"
CATALOG_PATH = Path(__file__).with_name("alphavantage_catalog.json")
QUERY_PREFIX = "https://www.alphavantage.co/query?"

_SECTION = re.compile(r'<(h[24]) id="([^"]+)"[^>]*>(.*?)</\1>', re.S)
_H6 = re.compile(r"<h6[^>]*>.*?</h6>", re.S)
_PARAM = re.compile(r"❚\s*(Required|Optional):\s*<code>(\w+)</code>")
_EXAMPLE_LINK = re.compile(r'<a href="(https://www\.alphavantage\.co/query\?[^"]+)"')
_CODE = re.compile(r"<code[^>]*>(.*?)</code>", re.S)
_ENUM_CUE = re.compile(r"(following values are supported|are supported|are accepted|is accepted|supported values|valid values)", re.I)
_TOKEN = re.compile(r"^[A-Za-z0-9_.\-+]+$")
_BADGES = {"popular-label": "trending", "premium-label": "premium", "utility-label": "utility"}


def _text(fragment: str) -> str:
    """Plain text of an HTML fragment with whitespace collapsed."""

    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _sentence_html(description_html: str) -> list[str]:
    """Sentences of a description, keeping the ``<code>`` markup so values can be told from prose."""

    return [part for part in re.split(r"(?<=[.!?])\s+(?![^<]*</code>)", description_html) if part.strip()]


def _codes(fragment: str) -> list[str]:
    return [_text(raw) for raw in _CODE.findall(fragment)]


_DATE_LIKE = re.compile(r"^(\d{4}(-\d{2}){0,2}|\d{4}Q\d|\d{8}T\d{4})$")


def _is_value(token: str) -> bool:
    return bool(_TOKEN.match(token)) and not token.replace(".", "", 1).isdigit() and not _DATE_LIKE.match(token)


def _enum_values(description_html: str, name: str) -> tuple[list[str], list[str]]:
    """``(strict, suggestions)``: values the docs state are accepted, and values only shown in ``name=value`` hints."""

    strict: list[str] = []
    hinted: list[str] = []
    plain = _text(description_html)
    for sentence in _sentence_html(description_html):
        codes = _codes(sentence)
        if _ENUM_CUE.search(_text(sentence)):
            head, colon, tail = sentence.partition(":")
            scan = _codes(head) or _codes(tail) if colon else codes
            strict += [c for c in scan if "=" not in c and _TOKEN.match(c) and c not in strict]
        for code in codes:
            key, _, value = code.partition("=")
            if key.strip() == name and value and _is_value(value.strip()) and value.strip() not in hinted:
                hinted.append(value.strip())
    integers = re.search(r"Integers (\d+) - (\d+) are accepted", plain)
    if integers and not strict:
        strict = [str(n) for n in range(int(integers.group(1)), int(integers.group(2)) + 1)]
    default = _default(plain, name)
    if hinted and default and default not in hinted and _is_value(default):
        hinted.insert(0, default)
    suggestions = [v for v in hinted if v not in strict] if strict else hinted
    return strict, suggestions if len(suggestions) >= 2 else []


def _enum_labels(description: str, values: list[str]) -> dict[str, str]:
    """Labels for numeric enums documented as ``0 = Simple Moving Average (SMA), 1 = ...``."""

    labels = {}
    for value, label in re.findall(r"(?<![\w.])(\d+) = ([^=]+?)(?=, \d+ = |\.|$)", description):
        if value in values:
            labels[value] = label.strip()
    return labels


def _default(description: str, name: str) -> str | None:
    match = re.search(rf"By default, `?{re.escape(name)}`?\s*=\s*([A-Za-z0-9_.\-]+)", description)
    return match.group(1) if match else None


def _example_value(description: str, name: str) -> str | None:
    """The value in the docs' own ``For example: name=value`` sentence."""

    match = re.search(rf"For example:?\s*{re.escape(name)}=(\S+?)(?=[\s,;&]|\.?$)", description)
    return match.group(1).rstrip(".") if match else None


def _param_type(name: str, strict: list[str], suggestions: list[str], description: str) -> str:
    if name == "function":
        return "fixed"
    values = set(strict) | set(suggestions)
    if values and values <= {"true", "false"}:
        return "boolean"
    if strict:
        return "enum"
    lowered = description.lower()
    if "positive integer" in lowered or "positive float" in lowered or name in {"time_period", "WINDOW_SIZE"}:
        return "number"
    if name == "date" or ("yyyy-mm-dd" in lowered and name != "month"):
        return "date"
    if name == "month":
        return "month"
    return "text"


def _parse_params(block: str) -> tuple[list[dict[str, Any]], str | None]:
    """Parameters and the ``function`` value of one endpoint section."""

    start = block.find("API Parameters")
    following = _H6.search(block, start + 1) if start >= 0 else None
    region = block[start : following.start() if following else len(block)] if start >= 0 else ""
    params: list[dict[str, Any]] = []
    function: str | None = None
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", region, re.S)
    current: dict[str, Any] | None = None
    parts: list[str] = []

    def close() -> None:
        nonlocal current, parts
        if current is None:
            return
        raw = " ".join(parts)
        description = _text(raw)
        name = current["name"]
        strict, suggestions = _enum_values(raw, name) if name != "function" else ([], [])
        ptype = _param_type(name, strict, suggestions, description)
        if ptype == "boolean":
            strict, suggestions = ["true", "false"], []
        premium = [sentence for sentence in _sentences(description) if "premium" in sentence.lower()]
        current.update(
            description=description,
            type=ptype,
            enum=strict,
            enum_labels=_enum_labels(description, strict),
            suggestions=suggestions,
            default=_default(description, name),
            example=_example_value(description, name),
            premium_note=" ".join(premium) or None,
        )
        params.append(current)
        current, parts = None, []

    for paragraph in paragraphs:
        match = _PARAM.search(paragraph)
        if match:
            close()
            current = {"name": match.group(2), "required": match.group(1) == "Required"}
            parts = [paragraph[match.end() :]]
            continue
        if current is not None:
            parts.append(paragraph)
    close()
    for param in params:
        if param["name"] == "function":
            found = re.search(r"function=([A-Z0-9_]+)", param["description"])
            function = found.group(1) if found else None
    return params, function


def _parse_examples(block: str, title: str) -> list[dict[str, Any]]:
    """Doc example links after the parameter list, each with its caption (an ``<i>`` note or the ``<h6>`` above)."""

    first = _H6.search(block, max(block.find("API Parameters"), 0) + 1)
    region = block[first.start() :] if first else ""
    guides = region.find("Language-specific guides")
    region = region[:guides] if guides >= 0 else region
    examples: list[dict[str, Any]] = []
    for link in _EXAMPLE_LINK.finditer(region):
        query: dict[str, Any] = {}
        for key, value in parse_qsl(urlsplit(html.unescape(link.group(1))).query):
            if key == "apikey":
                continue
            if key in query:
                query[key] = [*query[key], value] if isinstance(query[key], list) else [query[key], value]
            else:
                query[key] = value
        before = region[: link.start()]
        notes = re.findall(r"<i>(.*?)</i>", before[-700:], re.S)
        headings = _H6.findall(before)
        heading = re.sub(r"\s*\(click for JSON output\)\s*", "", _text(headings[-1])) if headings else ""
        caption = re.sub(r"^Examples?\s*[-:]\s*", "", _text(notes[-1]) if notes else heading)
        examples.append({"caption": caption if caption.lower() not in {"example", "examples"} else title, "params": query})
    seen: set[str] = set()
    unique = []
    for example in examples:
        key = json.dumps(example["params"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(example)
    return unique[:8]


def parse_documentation(document: str) -> dict[str, Any]:
    """Turns the documentation HTML into ``{"categories": [...], "endpoints": [...]}``."""

    matches = list(_SECTION.finditer(document))
    categories: list[dict[str, Any]] = []
    endpoints: list[dict[str, Any]] = []
    warnings: list[str] = []
    category = "General"
    for position, match in enumerate(matches):
        level, anchor, inner = match.group(1), match.group(2), match.group(3)
        end = matches[position + 1].start() if position + 1 < len(matches) else len(document)
        block = document[match.end() : end]
        if level == "h2":
            title = _text(inner).replace("\u2122", "")
            summary = _text(" ".join(re.findall(r"<p[^>]*>(.*?)</p>", block, re.S)[:1]))
            category = anchor
            categories.append({"id": anchor, "title": title, "summary": summary})
            continue
        badges = {_BADGES[cls]: True for cls in re.findall(r'class="([a-z-]*-label)"', inner) if cls in _BADGES}
        title = _text(re.sub(r"<span[^>]*>.*?</span>", "", inner, flags=re.S))
        params, function = _parse_params(block)
        examples = _parse_examples(block, title)
        repeated = {name for example in examples for name, value in example["params"].items() if isinstance(value, list)}
        for param in params:
            param["multiple"] = param["name"] in repeated
            if param["example"] is None:
                shown = next((e["params"][param["name"]] for e in examples if param["name"] in e["params"]), None)
                param["example"] = shown[0] if isinstance(shown, list) else shown
        if function is None and examples:
            function = examples[0]["params"].get("function")
        if function is None:
            warnings.append(f"{anchor}: no function name found; skipped")
            continue
        intro = block[: block.find("API Parameters")] if "API Parameters" in block else block
        paragraphs = [_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", intro, re.S)]
        description = " ".join(p for p in paragraphs if p)
        premium_notes = [s for p in paragraphs for s in _sentences(p) if "premium" in s.lower()]
        endpoints.append(
            {
                "function": function,
                "anchor": anchor,
                "title": title,
                "category": category,
                "description": description,
                "premium": bool(badges.get("premium")),
                "trending": bool(badges.get("trending")),
                "utility": bool(badges.get("utility")),
                "premium_notes": premium_notes,
                "params": [p for p in params if p["name"] not in {"function", "apikey"}],
                "examples": examples,
            }
        )
    return {"categories": categories, "endpoints": endpoints, "warnings": warnings}


# Functions documented in several sections get one title instead of the first section's.
_MERGED_TITLES = {"INDEX_DATA": "Index Data", "CURRENCY_EXCHANGE_RATE": "Currency Exchange Rate"}


def _merge_duplicates(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The docs describe a few functions twice (e.g. CURRENCY_EXCHANGE_RATE for FX and crypto)."""

    merged: dict[str, dict[str, Any]] = {}
    for endpoint in endpoints:
        existing = merged.get(endpoint["function"])
        if existing is None:
            merged[endpoint["function"]] = endpoint
            continue
        existing["title"] = _MERGED_TITLES.get(existing["function"], existing["title"])
        existing["premium"] = existing["premium"] or endpoint["premium"]
        existing["trending"] = existing["trending"] or endpoint["trending"]
        known = {p["name"] for p in existing["params"]}
        existing["params"] += [p for p in endpoint["params"] if p["name"] not in known]
        seen = {json.dumps(e["params"], sort_keys=True) for e in existing["examples"]}
        existing["examples"] += [e for e in endpoint["examples"] if json.dumps(e["params"], sort_keys=True) not in seen]
    return list(merged.values())


def build_catalog(document: str) -> dict[str, Any]:
    parsed = parse_documentation(document)
    endpoints = _merge_duplicates(parsed["endpoints"])
    return {
        "provider": "alphavantage",
        "source": DOCS_URL,
        "categories": parsed["categories"],
        "endpoints": endpoints,
        "warnings": parsed["warnings"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the Alpha Vantage endpoint catalog from its documentation.")
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    parser.add_argument("--html", type=Path, help="parse a saved copy of the page instead of downloading it")
    args = parser.parse_args(argv)
    if args.html:
        document = args.html.read_text(encoding="utf-8", errors="replace")
    else:
        response = requests.get(DOCS_URL, timeout=(5, 30), headers={"User-Agent": "tradingview-data-grabber catalog builder"})
        response.raise_for_status()
        document = response.text
    catalog = build_catalog(document)
    args.output.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    premium = sum(1 for e in catalog["endpoints"] if e["premium"])
    print(f"{len(catalog['endpoints'])} endpoints ({premium} premium) in {len(catalog['categories'])} categories -> {args.output}")
    for warning in catalog["warnings"]:
        print("warning:", warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
