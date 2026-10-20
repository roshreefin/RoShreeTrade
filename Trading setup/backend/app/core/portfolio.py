import json
import threading
import uuid
from datetime import datetime, date
from pathlib import Path
from app.config import BACKEND_DATA_DIR

POSITIONS_FILE = Path(BACKEND_DATA_DIR) / "portfolio.json"
_lock = threading.Lock()

_ALLOWED_SEGMENTS = {"INTRADAY", "SWING", "LONG-TERM", "MISC"}


def _read_raw() -> list[dict]:
    if not POSITIONS_FILE.exists():
        return []
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_raw(positions: list[dict]) -> None:
    with open(POSITIONS_FILE, "w", encoding="utf-8") as fh:
        json.dump(positions, fh, indent=2)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def list_positions() -> list[dict]:
    with _lock:
        return _read_raw()


def add_position(data: dict) -> dict | None:
    ticker = str(data.get("ticker") or "").strip().upper()
    qty = data.get("qty")
    avg_price = data.get("avg_price")
    if not ticker or qty is None or avg_price is None:
        return None
    try:
        qty = float(qty)
        avg_price = float(avg_price)
    except (TypeError, ValueError):
        return None
    if qty <= 0 or avg_price <= 0:
        return None

    segment = str(data.get("segment") or "MISC").upper()
    if segment not in _ALLOWED_SEGMENTS:
        segment = "MISC"

    position = {
        "id": uuid.uuid4().hex[:12],
        "ticker": ticker,
        "qty": round(qty, 4),
        "avg_price": round(avg_price, 2),
        "buy_date": str(data.get("buy_date") or _today()),
        "segment": segment,
        "stop_loss": round(float(data["stop_loss"]), 2) if data.get("stop_loss") not in (None, "") else None,
        "note": str(data.get("note") or "").strip() or None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    with _lock:
        positions = _read_raw()
        positions.append(position)
        _write_raw(positions)
    return position


def update_position(position_id: str, data: dict) -> dict | None:
    with _lock:
        positions = _read_raw()
        target = None
        for idx, p in enumerate(positions):
            if p.get("id") == position_id:
                target = (idx, p)
                break
        if target is None:
            return None
        idx, p = target
        for key in ("qty", "avg_price", "stop_loss", "buy_date", "segment", "note"):
            if key not in data or data[key] is None:
                continue
            if key == "segment":
                seg = str(data[key]).upper()
                p[key] = seg if seg in _ALLOWED_SEGMENTS else "MISC"
            elif key == "stop_loss":
                try:
                    p[key] = round(float(data[key]), 2)
                except (TypeError, ValueError):
                    pass
            elif key in ("qty", "avg_price"):
                try:
                    val = float(data[key])
                    if val > 0:
                        p[key] = round(val, 4 if key == "qty" else 2)
                except (TypeError, ValueError):
                    pass
            else:
                p[key] = str(data[key]).strip()
        _write_raw(positions)
        return p


def delete_position(position_id: str) -> bool:
    with _lock:
        positions = _read_raw()
        before = len(positions)
        positions = [p for p in positions if p.get("id") != position_id]
        removed = len(positions) != before
        _write_raw(positions)
        return removed