"""The .env reader: parsing, never overriding, names only."""

from __future__ import annotations

import os

import pytest

from tradingview_data.cli import build_parser
from tradingview_data.env import load_env_file

NAMES = ["TVD_A", "TVD_B", "TVD_C", "TVD_D", "TVD_E", "TVD_F"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    yield
    for name in NAMES:
        os.environ.pop(name, None)


def write(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_plain_export_quoted_and_commented_lines(tmp_path):
    path = write(tmp_path, "# a comment\n\nTVD_A=plain\nexport TVD_B = spaced value \nTVD_C=\"double # kept\"\nTVD_D='single'\nTVD_E=unquoted # trailing comment\n")
    assert load_env_file(path) == ["TVD_A", "TVD_B", "TVD_C", "TVD_D", "TVD_E"]
    assert (os.environ["TVD_A"], os.environ["TVD_B"], os.environ["TVD_C"], os.environ["TVD_D"], os.environ["TVD_E"]) == ("plain", "spaced value", "double # kept", "single", "unquoted")


def test_an_existing_variable_is_never_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("TVD_A", "from the shell")
    assert load_env_file(write(tmp_path, "TVD_A=from the file\nTVD_B=new\n")) == ["TVD_B"]
    assert os.environ["TVD_A"] == "from the shell"


def test_malformed_lines_a_missing_file_and_an_unreadable_file_are_skipped(tmp_path):
    assert load_env_file(write(tmp_path, "no equals sign\n=novalue\n1BAD=x\nTVD_F=ok\n")) == ["TVD_F"]
    assert load_env_file(tmp_path / "missing.env") == []
    assert load_env_file(tmp_path) == []  # a directory cannot be read as a file


def test_an_empty_value_is_set_as_empty(tmp_path):
    assert load_env_file(write(tmp_path, "TVD_A=\n")) == ["TVD_A"] and os.environ["TVD_A"] == ""


def test_only_names_are_returned_never_values(tmp_path):
    names = load_env_file(write(tmp_path, "TVD_A=supersecretvalue\n"))
    assert names == ["TVD_A"] and "supersecretvalue" not in repr(names)


def test_serve_accepts_an_env_file_option():
    args = build_parser().parse_args(["serve", "--env-file", "keys.env", "--state-dir", "s"])
    assert args.env_file == "keys.env"
    assert build_parser().parse_args(["serve"]).env_file is None
