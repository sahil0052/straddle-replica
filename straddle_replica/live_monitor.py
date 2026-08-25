from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
HISTORY_REPLAY_OVERLAP_MS = 300_000

TICK_FIELDS = (
    "time",
    "time_msc",
    "bid",
    "ask",
    "last",
    "volume",
    "volume_real",
    "flags",
)

POSITION_FIELDS = (
    "ticket",
    "time",
    "time_msc",
    "time_update",
    "time_update_msc",
    "type",
    "magic",
    "identifier",
    "reason",
    "volume",
    "price_open",
    "sl",
    "tp",
    "price_current",
    "swap",
    "profit",
    "symbol",
    "comment",
    "external_id",
)

ORDER_FIELDS = (
    "ticket",
    "time_setup",
    "time_setup_msc",
    "time_done",
    "time_done_msc",
    "time_expiration",
    "type",
    "type_time",
    "type_filling",
    "state",
    "magic",
    "position_id",
    "position_by_id",
    "reason",
    "volume_initial",
    "volume_current",
    "price_open",
    "sl",
    "tp",
    "price_current",
    "price_stoplimit",
    "symbol",
    "comment",
    "external_id",
)

POSITION_FINGERPRINT_EXCLUDED_FIELDS = frozenset(
    {"price_current", "profit", "swap"}
)
ORDER_FINGERPRINT_EXCLUDED_FIELDS = frozenset({"price_current"})

DEAL_FIELDS = (
    "ticket",
    "order",
    "time",
    "time_msc",
    "type",
    "entry",
    "magic",
    "position_id",
    "reason",
    "volume",
    "price",
    "commission",
    "swap",
    "profit",
    "fee",
    "symbol",
    "comment",
    "external_id",
)

RATE_FIELDS = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
)


class MonitorSafetyError(RuntimeError):
    """Raised when the collector is not attached to the approved read-only account."""


class MonitorConnectionError(RuntimeError):
    """Raised when the local MT5 terminal cannot provide monitoring data."""


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _record_value(record: object, name: str, default: Any = None) -> Any:
    dtype = getattr(record, "dtype", None)
    names = getattr(dtype, "names", None)
    if names and name in names:
        value = record[name]  # type: ignore[index]
        item = getattr(value, "item", None)
        return item() if callable(item) else value
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def normalize_record(record: object, fields: Sequence[str]) -> dict[str, Any]:
    return {field: _record_value(record, field) for field in fields}


def normalize_records(
    records: Iterable[object],
    fields: Sequence[str],
) -> list[dict[str, Any]]:
    normalized = [normalize_record(record, fields) for record in records]
    return sorted(
        normalized,
        key=lambda row: (
            int(row.get("ticket") or 0),
            int(row.get("time_msc") or row.get("time_setup_msc") or 0),
        ),
    )


def tick_identity(tick: object) -> tuple[Any, ...]:
    return tuple(_record_value(tick, field) for field in TICK_FIELDS)


class TickDeduplicator:
    def __init__(self, max_seen: int = 100_000) -> None:
        if max_seen <= 0:
            raise ValueError("max_seen must be positive")
        self._max_seen = max_seen
        self._order: deque[tuple[Any, ...]] = deque()
        self._seen: set[tuple[Any, ...]] = set()

    def filter(self, ticks: Iterable[object]) -> list[object]:
        unique: list[object] = []
        for tick in ticks:
            identity = tick_identity(tick)
            if identity in self._seen:
                continue
            self._seen.add(identity)
            self._order.append(identity)
            unique.append(tick)
            while len(self._order) > self._max_seen:
                expired = self._order.popleft()
                self._seen.discard(expired)
        return unique


def state_fingerprint(
    positions: Sequence[Mapping[str, Any]],
    orders: Sequence[Mapping[str, Any]],
) -> str:
    def canonical(
        rows: Sequence[Mapping[str, Any]],
        excluded_fields: frozenset[str],
    ) -> list[dict[str, Any]]:
        values = [
            {
                key: value
                for key, value in row.items()
                if key not in excluded_fields
            }
            for row in rows
        ]
        return sorted(
            values,
            key=lambda row: (
                int(row.get("ticket") or 0),
                json.dumps(row, sort_keys=True, separators=(",", ":"), default=str),
            ),
        )

    payload = {
        "orders": canonical(orders, ORDER_FINGERPRINT_EXCLUDED_FIELDS),
        "positions": canonical(
            positions,
            POSITION_FINGERPRINT_EXCLUDED_FIELDS,
        ),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def hourly_path(
    root: str | Path,
    prefix: str,
    when: datetime,
    suffix: str,
) -> Path:
    hour = when.astimezone(UTC).strftime("%Y%m%d-%H")
    return Path(root) / f"{prefix}-{hour}{suffix}"


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def validate_read_only_account(
    account: object,
    *,
    expected_login: int,
    expected_server: str,
    require_read_only: bool,
) -> None:
    actual_login = int(_record_value(account, "login", 0) or 0)
    actual_server = str(_record_value(account, "server", "") or "")
    trade_allowed = bool(_record_value(account, "trade_allowed", False))

    if actual_login != expected_login:
        raise MonitorSafetyError(
            f"Unexpected account login {actual_login}; expected {expected_login}"
        )
    if actual_server != expected_server:
        raise MonitorSafetyError(
            f"Unexpected account server {actual_server!r}; "
            f"expected {expected_server!r}"
        )
    if require_read_only and trade_allowed:
        raise MonitorSafetyError(
            "Monitoring refused because account trading is allowed"
        )


def _public_record(record: object, excluded: set[str] | None = None) -> dict[str, Any]:
    excluded = excluded or set()
    if hasattr(record, "_asdict"):
        source = record._asdict()
    elif isinstance(record, Mapping):
        source = record
    else:
        return {}
    return {
        key: value
        for key, value in source.items()
        if key not in excluded
    }


@dataclass(frozen=True)
class LiveMonitorConfig:
    terminal_path: Path
    output_root: Path
    symbol: str = "XAUUSD"
    expected_login: int = 901018
    expected_server: str = "AchieverGlobalMarkets-Server"
    require_read_only: bool = True
    poll_ms: int = 50
    checkpoint_seconds: float = 5.0
    history_poll_seconds: float = 0.25
    history_seed_days: float = 0.0
    history_rates_timeframe: str = ""
    history_rates_seed_days: float = 0.0
    heartbeat_seconds: float = 1.0
    duration_hours: float = 0.0
    exit_on_connection_error: bool = False

    def validate(self) -> None:
        if self.poll_ms < 20:
            raise ValueError("poll_ms must be at least 20")
        if self.checkpoint_seconds <= 0:
            raise ValueError("checkpoint_seconds must be positive")
        if self.history_poll_seconds <= 0:
            raise ValueError("history_poll_seconds must be positive")
        if self.history_seed_days < 0:
            raise ValueError("history_seed_days cannot be negative")
        if self.history_rates_seed_days < 0:
            raise ValueError("history_rates_seed_days cannot be negative")
        has_rates_timeframe = bool(self.history_rates_timeframe.strip())
        has_rates_seed = self.history_rates_seed_days > 0
        if has_rates_timeframe != has_rates_seed:
            raise ValueError(
                "history_rates_timeframe and history_rates_seed_days "
                "must be supplied together"
            )
        if self.heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if self.duration_hours < 0:
            raise ValueError("duration_hours cannot be negative")


class HourlyCaptureStore:
    def __init__(self, output_root: Path, session_id: str) -> None:
        self.output_root = output_root.resolve()
        self.session_id = session_id
        self.session_dir = self.output_root / session_id
        self.session_dir.mkdir(parents=True, exist_ok=False)
        self._csv_files: dict[tuple[str, str], tuple[Any, csv.DictWriter]] = {}
        self._jsonl_files: dict[tuple[str, str], Any] = {}
        atomic_write_json(
            self.output_root / "current-session.json",
            {
                "session_id": session_id,
                "session_dir": str(self.session_dir),
            },
        )

    def write_manifest(self, value: Mapping[str, Any]) -> None:
        atomic_write_json(self.session_dir / "manifest.json", value)

    def append_csv(
        self,
        prefix: str,
        when: datetime,
        rows: Sequence[Mapping[str, Any]],
        fieldnames: Sequence[str],
    ) -> None:
        if not rows:
            return
        hour = when.astimezone(UTC).strftime("%Y%m%d-%H")
        key = (prefix, hour)
        if key not in self._csv_files:
            path = hourly_path(self.session_dir, prefix, when, ".csv")
            is_new = not path.exists() or path.stat().st_size == 0
            handle = path.open("a", encoding="utf-8", newline="", buffering=1)
            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                extrasaction="ignore",
            )
            if is_new:
                writer.writeheader()
                handle.flush()
            self._csv_files[key] = (handle, writer)
            self._close_old_csv(prefix, hour)
        handle, writer = self._csv_files[key]
        writer.writerows(rows)
        handle.flush()

    def append_jsonl(
        self,
        prefix: str,
        when: datetime,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        if not rows:
            return
        hour = when.astimezone(UTC).strftime("%Y%m%d-%H")
        key = (prefix, hour)
        if key not in self._jsonl_files:
            path = hourly_path(self.session_dir, prefix, when, ".jsonl")
            handle = path.open("a", encoding="utf-8", buffering=1)
            self._jsonl_files[key] = handle
            self._close_old_jsonl(prefix, hour)
        handle = self._jsonl_files[key]
        for row in rows:
            handle.write(
                json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
                + "\n"
            )
        handle.flush()

    def write_heartbeat(self, value: Mapping[str, Any]) -> None:
        atomic_write_json(self.session_dir / "heartbeat.json", value)

    def _close_old_csv(self, prefix: str, current_hour: str) -> None:
        for key in list(self._csv_files):
            if key[0] == prefix and key[1] != current_hour:
                handle, _ = self._csv_files.pop(key)
                handle.close()

    def _close_old_jsonl(self, prefix: str, current_hour: str) -> None:
        for key in list(self._jsonl_files):
            if key[0] == prefix and key[1] != current_hour:
                self._jsonl_files.pop(key).close()

    def close(self) -> None:
        for handle, _ in self._csv_files.values():
            handle.close()
        for handle in self._jsonl_files.values():
            handle.close()
        self._csv_files.clear()
        self._jsonl_files.clear()


class MetaTrader5ReadAdapter:
    def __init__(
        self,
        terminal_path: Path,
        symbol: str,
        *,
        expected_login: int,
        expected_server: str,
    ) -> None:
        self.terminal_path = terminal_path
        self.symbol = symbol
        self.expected_login = expected_login
        self.expected_server = expected_server
        self._mt5: Any = None

    @property
    def module(self) -> Any:
        if self._mt5 is None:
            raise MonitorConnectionError("MT5 adapter is not connected")
        return self._mt5

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise MonitorConnectionError(
                "MetaTrader5 Python package is not installed"
            ) from exc
        self._mt5 = mt5
        if not mt5.initialize(
            path=str(self.terminal_path),
            portable=True,
            login=self.expected_login,
            server=self.expected_server,
        ):
            error = mt5.last_error()
            self._mt5 = None
            raise MonitorConnectionError(
                f"MT5 initialize failed for {self.terminal_path}: {error}"
            )
        symbol = mt5.symbol_info(self.symbol)
        if symbol is None:
            error = mt5.last_error()
            self.disconnect()
            raise MonitorConnectionError(
                f"Symbol {self.symbol!r} is unavailable: {error}"
            )
        if not bool(getattr(symbol, "visible", False)):
            if not mt5.symbol_select(self.symbol, True):
                error = mt5.last_error()
                self.disconnect()
                raise MonitorConnectionError(
                    f"Unable to select symbol {self.symbol!r}: {error}"
                )

    def disconnect(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None

    def account_info(self) -> object:
        value = self.module.account_info()
        if value is None:
            raise MonitorConnectionError(
                f"MT5 account_info failed: {self.module.last_error()}"
            )
        return value

    def terminal_info(self) -> object:
        value = self.module.terminal_info()
        if value is None:
            raise MonitorConnectionError(
                f"MT5 terminal_info failed: {self.module.last_error()}"
            )
        return value

    def symbol_info(self) -> object:
        value = self.module.symbol_info(self.symbol)
        if value is None:
            raise MonitorConnectionError(
                f"MT5 symbol_info failed: {self.module.last_error()}"
            )
        return value

    def positions(self) -> Sequence[object]:
        value = self.module.positions_get()
        if value is None:
            raise MonitorConnectionError(
                f"MT5 positions_get failed: {self.module.last_error()}"
            )
        return value

    def orders(self) -> Sequence[object]:
        value = self.module.orders_get()
        if value is None:
            raise MonitorConnectionError(
                f"MT5 orders_get failed: {self.module.last_error()}"
            )
        return value

    def ticks(self, start: datetime, end: datetime) -> Sequence[object]:
        value = self.module.copy_ticks_range(
            self.symbol,
            start,
            end,
            self.module.COPY_TICKS_ALL,
        )
        if value is None:
            raise MonitorConnectionError(
                f"MT5 copy_ticks_range failed: {self.module.last_error()}"
            )
        return value

    def rates(
        self,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[object]:
        normalized = timeframe.strip().upper()
        constant_name = f"TIMEFRAME_{normalized}"
        if not hasattr(self.module, constant_name):
            raise ValueError(
                f"Unsupported MT5 timeframe: {timeframe!r}"
            )
        value = self.module.copy_rates_range(
            self.symbol,
            getattr(self.module, constant_name),
            start,
            end,
        )
        if value is None:
            raise MonitorConnectionError(
                f"MT5 copy_rates_range failed: {self.module.last_error()}"
            )
        return value

    def history_orders(
        self,
        start: datetime,
        end: datetime,
    ) -> Sequence[object]:
        value = self.module.history_orders_get(start, end)
        if value is None:
            raise MonitorConnectionError(
                f"MT5 history_orders_get failed: {self.module.last_error()}"
            )
        return value

    def history_deals(
        self,
        start: datetime,
        end: datetime,
    ) -> Sequence[object]:
        value = self.module.history_deals_get(start, end)
        if value is None:
            raise MonitorConnectionError(
                f"MT5 history_deals_get failed: {self.module.last_error()}"
            )
        return value


class LiveMonitor:
    def __init__(
        self,
        config: LiveMonitorConfig,
        adapter: MetaTrader5ReadAdapter,
        store: HourlyCaptureStore,
    ) -> None:
        config.validate()
        self.config = config
        self.adapter = adapter
        self.store = store
        self.started_at = utc_now()
        self._tick_deduplicator = TickDeduplicator()
        self._last_tick_msc = 0
        self._last_state_fingerprint = ""
        self._last_checkpoint = datetime.min.replace(tzinfo=UTC)
        self._last_history_poll = datetime.min.replace(tzinfo=UTC)
        self._last_heartbeat = datetime.min.replace(tzinfo=UTC)
        self._history_server_offset = timedelta(0)
        history_seed = (
            timedelta(days=self.config.history_seed_days)
            if self.config.history_seed_days > 0
            else timedelta(minutes=1)
        )
        self._history_from_msc = int(
            (self.started_at - history_seed).timestamp() * 1000
        )
        self._seen_history_orders: set[int] = set()
        self._seen_history_deals: set[int] = set()
        self._sequence = 0
        self._snapshot_count = 0
        self._tick_count = 0
        self._history_order_count = 0
        self._history_deal_count = 0
        self._history_rate_count = 0
        self._reconnect_count = 0
        self._last_error = ""
        self._positions_total = 0
        self._orders_total = 0

    def _previous_history_server_offset(self) -> timedelta | None:
        manifests = sorted(
            self.store.output_root.glob("*/manifest.json"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for path in manifests:
            if path.parent == self.store.session_dir:
                continue
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                account = manifest.get("account") or {}
                symbol = manifest.get("symbol") or {}
                time_domains = manifest.get("time_domains") or {}
                offset_seconds = int(
                    time_domains.get("history_server_offset_seconds")
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                int(account.get("login") or 0)
                != self.config.expected_login
                or str(account.get("server") or "")
                != self.config.expected_server
                or str(symbol.get("name") or "") != self.config.symbol
                or offset_seconds == 0
                or abs(offset_seconds) > 14 * 60 * 60
            ):
                continue
            return timedelta(seconds=offset_seconds)
        return None

    def initialize(self) -> None:
        self.adapter.connect()
        account = self.adapter.account_info()
        validate_read_only_account(
            account,
            expected_login=self.config.expected_login,
            expected_server=self.config.expected_server,
            require_read_only=self.config.require_read_only,
        )
        terminal = self.adapter.terminal_info()
        symbol = self.adapter.symbol_info()
        history_server_offset_source = "default_zero"
        symbol_time = int(_record_value(symbol, "time", 0) or 0)
        if symbol_time > 0:
            raw_offset = symbol_time - self.started_at.timestamp()
            rounded_offset = round(raw_offset / 900) * 900
            if (
                abs(rounded_offset) <= 14 * 60 * 60
                and abs(raw_offset - rounded_offset) <= 120
            ):
                self._history_server_offset = timedelta(
                    seconds=rounded_offset
                )
                history_server_offset_source = "symbol_time"
        if history_server_offset_source == "default_zero":
            previous_offset = self._previous_history_server_offset()
            if previous_offset is not None:
                self._history_server_offset = previous_offset
                history_server_offset_source = "previous_manifest"
        self.store.write_manifest(
            {
                "schema_version": 1,
                "session_id": self.store.session_id,
                "started_at_utc": self.started_at.isoformat(),
                "process_id": os.getpid(),
                "config": {
                    **asdict(self.config),
                    "terminal_path": str(self.config.terminal_path),
                    "output_root": str(self.config.output_root),
                },
                "account": _public_record(
                    account,
                    excluded={
                        "balance",
                        "credit",
                        "equity",
                        "margin",
                        "margin_free",
                        "margin_level",
                        "assets",
                        "liabilities",
                        "commission_blocked",
                    },
                ),
                "terminal": _public_record(terminal),
                "symbol": _public_record(symbol),
                "safety": {
                    "account_trade_allowed": bool(
                        _record_value(account, "trade_allowed", False)
                    ),
                    "require_read_only": self.config.require_read_only,
                    "collector_has_trading_api": False,
                },
                "time_domains": {
                    "history_server_offset_seconds": int(
                        self._history_server_offset.total_seconds()
                    ),
                    "history_server_offset_source": (
                        history_server_offset_source
                    ),
                },
            }
        )
        self._capture_history_rates()
        self.capture_once(force_checkpoint=True)

    def capture_once(self, force_checkpoint: bool = False) -> None:
        now = utc_now()
        account = self.adapter.account_info()
        validate_read_only_account(
            account,
            expected_login=self.config.expected_login,
            expected_server=self.config.expected_server,
            require_read_only=self.config.require_read_only,
        )

        self._capture_ticks(now)
        self._capture_state(now, force_checkpoint=force_checkpoint)
        if (
            now - self._last_history_poll
        ).total_seconds() >= self.config.history_poll_seconds:
            self._capture_history(now)
            self._last_history_poll = now
        if (
            now - self._last_heartbeat
        ).total_seconds() >= self.config.heartbeat_seconds:
            self._write_heartbeat(now, healthy=True)
            self._last_heartbeat = now
        self._sequence += 1

    def _capture_ticks(self, now: datetime) -> None:
        broker_now = now + self._history_server_offset
        if self._last_tick_msc:
            start_msc = max(0, self._last_tick_msc - 1_000)
            start = datetime.fromtimestamp(start_msc / 1000, tz=UTC)
        else:
            start = broker_now - timedelta(seconds=10)
        ticks = self.adapter.ticks(
            start,
            broker_now + timedelta(seconds=1),
        )
        unique = self._tick_deduplicator.filter(ticks)
        rows: list[dict[str, Any]] = []
        capture_time = now.isoformat()
        monotonic_ns = time.monotonic_ns()
        for tick in unique:
            row = normalize_record(tick, TICK_FIELDS)
            row["capture_time_utc"] = capture_time
            row["capture_monotonic_ns"] = monotonic_ns
            rows.append(row)
            self._last_tick_msc = max(
                self._last_tick_msc,
                int(row.get("time_msc") or 0),
            )
        self.store.append_csv(
            "ticks",
            now,
            rows,
            (
                "capture_time_utc",
                "capture_monotonic_ns",
                *TICK_FIELDS,
            ),
        )
        self._tick_count += len(rows)

    def _capture_state(
        self,
        now: datetime,
        *,
        force_checkpoint: bool,
    ) -> None:
        positions = normalize_records(self.adapter.positions(), POSITION_FIELDS)
        orders = normalize_records(self.adapter.orders(), ORDER_FIELDS)
        fingerprint = state_fingerprint(positions, orders)
        checkpoint_due = (
            now - self._last_checkpoint
        ).total_seconds() >= self.config.checkpoint_seconds
        changed = fingerprint != self._last_state_fingerprint
        self._positions_total = len(positions)
        self._orders_total = len(orders)
        if not (changed or checkpoint_due or force_checkpoint):
            return
        reason = "initial" if not self._last_state_fingerprint else (
            "change" if changed else "checkpoint"
        )
        self.store.append_jsonl(
            "snapshots",
            now,
            [
                {
                    "capture_time_utc": now.isoformat(),
                    "capture_monotonic_ns": time.monotonic_ns(),
                    "sequence": self._sequence,
                    "reason": reason,
                    "fingerprint": fingerprint,
                    "positions": positions,
                    "orders": orders,
                }
            ],
        )
        self._snapshot_count += 1
        self._last_state_fingerprint = fingerprint
        self._last_checkpoint = now

    def _capture_history(self, now: datetime) -> None:
        start = datetime.fromtimestamp(
            max(0, self._history_from_msc - HISTORY_REPLAY_OVERLAP_MS) / 1000,
            tz=UTC,
        )
        end = now + self._history_server_offset + timedelta(seconds=1)
        historical_orders = normalize_records(
            self.adapter.history_orders(start, end),
            ORDER_FIELDS,
        )
        deals = normalize_records(
            self.adapter.history_deals(start, end),
            DEAL_FIELDS,
        )
        new_orders = [
            row
            for row in historical_orders
            if int(row.get("ticket") or 0) not in self._seen_history_orders
        ]
        new_deals = [
            row
            for row in deals
            if int(row.get("ticket") or 0) not in self._seen_history_deals
        ]
        for row in new_orders:
            self._seen_history_orders.add(int(row.get("ticket") or 0))
            row["capture_time_utc"] = now.isoformat()
        for row in new_deals:
            self._seen_history_deals.add(int(row.get("ticket") or 0))
            row["capture_time_utc"] = now.isoformat()
        self.store.append_jsonl("history-orders", now, new_orders)
        self.store.append_jsonl("history-deals", now, new_deals)
        self._history_order_count += len(new_orders)
        self._history_deal_count += len(new_deals)

        latest_times = [
            int(row.get("time_done_msc") or row.get("time_setup_msc") or 0)
            for row in historical_orders
        ] + [int(row.get("time_msc") or 0) for row in deals]
        if latest_times:
            self._history_from_msc = max(
                self._history_from_msc,
                max(latest_times),
            )

    def _capture_history_rates(self) -> None:
        timeframe = self.config.history_rates_timeframe.strip().upper()
        if not timeframe:
            return
        now = utc_now()
        start = self.started_at - timedelta(
            days=self.config.history_rates_seed_days
        )
        end = (
            self.started_at
            + self._history_server_offset
            + timedelta(seconds=1)
        )
        rates = [
            normalize_record(rate, RATE_FIELDS)
            for rate in self.adapter.rates(timeframe, start, end)
        ]
        rates.sort(key=lambda row: int(row.get("time") or 0))
        capture_time = now.isoformat()
        for row in rates:
            row["capture_time_utc"] = capture_time
            row["timeframe"] = timeframe
        self.store.append_jsonl(
            f"history-rates-{timeframe}",
            now,
            rates,
        )
        self._history_rate_count += len(rates)

    def _write_heartbeat(
        self,
        now: datetime,
        *,
        healthy: bool,
        stopped: bool = False,
    ) -> None:
        self.store.write_heartbeat(
            {
                "schema_version": 1,
                "session_id": self.store.session_id,
                "capture_time_utc": now.isoformat(),
                "process_id": os.getpid(),
                "healthy": healthy,
                "stopped": stopped,
                "read_only_verified": True,
                "sequence": self._sequence,
                "last_tick_msc": self._last_tick_msc,
                "positions_total": self._positions_total,
                "orders_total": self._orders_total,
                "tick_count": self._tick_count,
                "snapshot_count": self._snapshot_count,
                "history_order_count": self._history_order_count,
                "history_deal_count": self._history_deal_count,
                "history_rate_count": self._history_rate_count,
                "reconnect_count": self._reconnect_count,
                "last_error": self._last_error,
            }
        )

    def run(self) -> None:
        deadline = (
            self.started_at + timedelta(hours=self.config.duration_hours)
            if self.config.duration_hours > 0
            else None
        )
        try:
            while deadline is None or utc_now() < deadline:
                cycle_started = time.monotonic()
                try:
                    self.capture_once()
                    self._last_error = ""
                except MonitorSafetyError:
                    raise
                except Exception as exc:
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._write_heartbeat(utc_now(), healthy=False)
                    if self.config.exit_on_connection_error:
                        raise
                    self._reconnect()
                elapsed = time.monotonic() - cycle_started
                delay = max(0.0, self.config.poll_ms / 1000 - elapsed)
                if delay:
                    time.sleep(delay)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                self._write_heartbeat(
                    utc_now(),
                    healthy=not bool(self._last_error),
                    stopped=True,
                )
            finally:
                self.adapter.disconnect()
                self.store.close()

    def _reconnect(self) -> bool:
        self.adapter.disconnect()
        time.sleep(1.0)
        try:
            self.adapter.connect()
            account = self.adapter.account_info()
        except MonitorConnectionError as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return False
        validate_read_only_account(
            account,
            expected_login=self.config.expected_login,
            expected_server=self.config.expected_server,
            require_read_only=self.config.require_read_only,
        )
        self._reconnect_count += 1
        return True


def create_session_id(
    expected_login: int,
    symbol: str,
    now: datetime | None = None,
) -> str:
    timestamp = (now or utc_now()).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_symbol = "".join(
        character
        for character in symbol
        if character.isalnum() or character in {"-", "_"}
    )
    return f"{timestamp}_{expected_login}_{safe_symbol}"


def run_live_monitor(config: LiveMonitorConfig) -> Path:
    config.validate()
    session_id = create_session_id(config.expected_login, config.symbol)
    store = HourlyCaptureStore(config.output_root, session_id)
    adapter = MetaTrader5ReadAdapter(
        config.terminal_path,
        config.symbol,
        expected_login=config.expected_login,
        expected_server=config.expected_server,
    )
    monitor = LiveMonitor(config, adapter, store)
    try:
        monitor.initialize()
        monitor.run()
    except Exception:
        adapter.disconnect()
        store.close()
        raise
    return store.session_dir


def read_monitor_status(output_root: Path) -> dict[str, Any]:
    pointer = output_root / "current-session.json"
    if not pointer.exists():
        raise FileNotFoundError(f"No monitor session pointer found at {pointer}")
    current = json.loads(pointer.read_text(encoding="utf-8"))
    session_dir = Path(current["session_dir"])
    heartbeat_path = session_dir / "heartbeat.json"
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    heartbeat["session_dir"] = str(session_dir)
    heartbeat["heartbeat_path"] = str(heartbeat_path)
    return heartbeat
