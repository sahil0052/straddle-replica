from __future__ import annotations

import json
import sys

import MetaTrader5 as mt5
import numpy


EXPECTED_LOGIN = 901018
EXPECTED_SERVER = "AchieverGlobalMarkets-Server"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_wine_monitor.py TERMINAL_PATH")

    terminal_path = sys.argv[1]
    if not mt5.initialize(path=terminal_path, portable=True):
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        positions = mt5.positions_get()
        orders = mt5.orders_get()
        if account is None or terminal is None:
            raise SystemExit(f"MT5 account/terminal query failed: {mt5.last_error()}")
        if account.login != EXPECTED_LOGIN:
            raise SystemExit(f"unexpected account login: {account.login}")
        if account.server != EXPECTED_SERVER:
            raise SystemExit(f"unexpected account server: {account.server}")
        if account.trade_allowed:
            raise SystemExit("refusing monitor verification: account can trade")
        if not terminal.connected:
            raise SystemExit("MT5 terminal is not connected")

        print(
            json.dumps(
                {
                    "connected": bool(terminal.connected),
                    "login": int(account.login),
                    "numpy_version": numpy.__version__,
                    "orders": None if orders is None else len(orders),
                    "positions": None if positions is None else len(positions),
                    "read_only": not bool(account.trade_allowed),
                    "server": account.server,
                    "trade_allowed": bool(account.trade_allowed),
                    "mt5_version": mt5.__version__,
                },
                sort_keys=True,
            )
        )
    finally:
        mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
