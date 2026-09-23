# Retired experimental notebook

The former heartbeat notebook was removed because it included a credential-like
value in its source. Use the modular CLI instead:

```bash
tvdata bars -n BINANCE:BTCUSDT -t 1 -b 300
tvdata quote -n BINANCE:BTCUSDT --price-only
```

Do not place account tokens, passwords, or authenticated websocket captures in
notebooks. Keep them in environment variables or an approved secret manager.
