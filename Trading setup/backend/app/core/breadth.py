import time
from datetime import datetime
from app.config import settings
from app.core.chart_analysis import chart_analyzer

BREADTH_CACHE_TTL_SECONDS = 60


class MarketBreadth:
    def __init__(self):
        self._cache = None
        self._cache_ts = 0

    def compute(self) -> dict:
        now = time.time()
        if self._cache and now - self._cache_ts < BREADTH_CACHE_TTL_SECONDS:
            return self._cache

        advances = 0
        declines = 0
        unchanged = 0
        highs_3m = 0
        lows_3m = 0
        total = 0

        for symbol in settings.NIFTY_200_SYMBOLS:
            snap = chart_analyzer.get_latest_and_prev(symbol)
            if snap is None:
                continue
            last, prev, hi3, lo3 = snap
            total += 1
            if last > prev:
                advances += 1
            elif last < prev:
                declines += 1
            else:
                unchanged += 1
            if last >= hi3:
                highs_3m += 1
            if last <= lo3:
                lows_3m += 1

        if total < 50:
            self._cache = {
                "advances": None, "declines": None, "unchanged": None, "total": None,
                "advance_decline_ratio": None, "breadth_status": "unavailable",
                "week52_high": None, "week52_low": None, "high_low_ratio": None,
                "available": False, "scope": f"NIFTY-200 universe",
                "disclaimer": "Could not collect enough live quotes to compute breadth.",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._cache_ts = time.time()
            return self._cache

        adr = round(advances / declines, 2) if declines else None
        if declines and advances >= 1.5 * declines:
            status = "strong"
        elif advances and declines >= 1.5 * advances:
            status = "weak"
        else:
            status = "mixed"
        hl_ratio = round(highs_3m / max(lows_3m, 1), 2)

        self._cache = {
            "advances": advances, "declines": declines, "unchanged": unchanged,
            "total": total,
            "advance_decline_ratio": adr,
            "breadth_status": status,
            "week52_high": highs_3m, "week52_low": lows_3m,
            "high_low_ratio": hl_ratio,
            "available": True,
            "scope": "NIFTY-200 universe",
            "breadth_note": "Computed live from last vs previous daily close for all scanned NIFTY-200 symbols.",
            "highlow_note": "Highs/Lows are relative to the trailing 3-month window used for chart history.",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._cache_ts = time.time()
        return self._cache


market_breadth = MarketBreadth()