"""Trading through the Alpaca Trading API, for a paper or a live account.

``client`` talks to Alpaca, ``validation`` checks every request before anything is sent, ``views``
turns Alpaca's answers into the shapes the dashboard draws, ``service`` ties them together and
``routes`` serves them under ``/api/trading``.
"""
