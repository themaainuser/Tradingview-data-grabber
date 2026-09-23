"""Compatibility entry point for authenticated session-token retrieval."""

from tradingview_data.auth import get_auth_token
from tradingview_data.cli import legacy_auth_main

__all__ = ["get_auth_token"]


def main():
    return legacy_auth_main()


if __name__ == "__main__":
    raise SystemExit(main())
