import logging
import time
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

FII_DII_CACHE_TTL_SECONDS = 900
SOURCE_TIMEOUT_SECONDS = 12

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json, text/plain, */*",
}

NSE_FII_PAGE = "https://www.nseindia.com/market-analysis/fii-dii"
NSE_FII_API = "https://www.nseindia.com/api/fiidiiTradeReact"
MONEYCONTROL_JSON = "https://www.moneycontrol.com/menubar/json/fiidii_combined.json"


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict) -> dict | None:
    date_val = None
    fii = None
    dii = None
    for key, value in row.items():
        key_l = str(key).lower()
        if key_l == "date":
            date_val = str(value)
        elif "fii" in key_l and "cash" in key_l and fii is None:
            fii = _to_float(value)
        elif "dii" in key_l and "cash" in key_l and dii is None:
            dii = _to_float(value)
    if fii is None:
        raise ValueError("no FII field found")
    if dii is None:
        raise ValueError("no DII field found")
    return {"date": date_val, "fii_crore": fii, "dii_crore": dii}


def _parse_rows(raw) -> list[dict]:
    rows = []
    if isinstance(raw, dict):
        seq = raw.get("seq") or raw.get("data") or raw.get("rows") or raw.get("result")
        if isinstance(seq, list):
            raw = seq
        else:
            return []
    if not isinstance(raw, list):
        return []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            rows.append(_parse_row(item))
        except ValueError:
            continue
    return rows


def _fetch_nse() -> list[dict]:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=SOURCE_TIMEOUT_SECONDS, follow_redirects=True) as client:
        client.get(NSE_FII_PAGE)
        resp = client.get(NSE_FII_API)
        resp.raise_for_status()
        return _parse_rows(resp.json())


def _fetch_moneycontrol() -> list[dict]:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=SOURCE_TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = client.get(MONEYCONTROL_JSON)
        resp.raise_for_status()
        return _parse_rows(resp.json())


class FiiDiiProvider:
    def __init__(self):
        self._cache = None
        self._cache_ts = 0
        self._source = None

    def _build_result(self, available: bool, rows: list[dict] | None = None, source: str | None = None) -> dict:
        if not available or not rows:
            return {
                "daily": [],
                "summary": None,
                "disclaimer": "Live FII/DII data sources (NSE India, MoneyControl) are unreachable from this network right now. Data appears once a source responds.",
                "source": None,
                "available": False,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        recent = rows[:30]
        total_fii = round(sum(r["fii_crore"] for r in recent), 2)
        total_dii = round(sum(r["dii_crore"] for r in recent), 2)
        net = round(total_fii + total_dii, 2)
        fii_trend = "bullish" if net >= 0 else "bearish"
        return {
            "daily": recent,
            "summary": {
                "total_fii_crore": total_fii,
                "total_dii_crore": total_dii,
                "net_crore": net,
                "fii_trend": fii_trend,
            },
            "disclaimer": "Figures shown are as published by the source (NSE India / MoneyControl). FII/DII provisional cash market data, values in Rs crore.",
            "source": source,
            "available": True,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def fetch(self) -> dict:
        now = time.time()
        if self._cache and now - self._cache_ts < FII_DII_CACHE_TTL_SECONDS:
            return self._cache

        result = None
        for name, fetcher in (("NSE India", _fetch_nse), ("MoneyControl", _fetch_moneycontrol)):
            try:
                rows = fetcher()
                if rows:
                    result = self._build_result(True, rows, name)
                    self._source = name
                    break
            except Exception as e:
                logger.warning("[fiidii] %s source failed: %s", name, e)

        if result is None:
            result = self._build_result(False)

        self._cache = result
        self._cache_ts = time.time()
        return result


fiidii_provider = FiiDiiProvider()