import threading
from datetime import datetime
from app.core.momentum import MomentumStrategy
from app.core.swing import VCPStrategy
from app.core.positional import Stage2BreakoutStrategy
from app.models.schemas import ScanResult


class SignalScanner:
    def __init__(self):
        self.intraday = MomentumStrategy()
        self.swing = VCPStrategy()
        self.positional = Stage2BreakoutStrategy()
        self._cache = None
        self._cache_time = None
        self._lock = threading.Lock()
        self._scanning = False

    def _fresh_cache(self, market_status: str) -> ScanResult | None:
        now = datetime.now()
        if self._cache and self._cache_time:
            if (now - self._cache_time).total_seconds() < 300 and self._cache.market_status == market_status:
                return self._cache
        return None

    def get_cached(self, market_status: str) -> ScanResult | None:
        return self._fresh_cache(market_status)

    def get_signal_for(self, ticker: str) -> dict | None:
        if not self._cache:
            return None
        for s in self._cache.signals:
            if s.ticker == ticker.upper():
                return s.model_dump()
        return None

    def get_signal_map(self) -> dict[str, str]:
        if not self._cache:
            return {}
        return {s.ticker: s.segment for s in self._cache.signals}

    def is_scanning(self) -> bool:
        return self._scanning

    def run_full_scan(self, market_status: str, quick: bool = True) -> ScanResult:
        now = datetime.now()
        if self._cache and self._cache_time:
            if (now - self._cache_time).total_seconds() < 300 and self._cache.market_status == market_status:
                return self._cache

        with self._lock:
            now = datetime.now()
            if self._cache and self._cache_time:
                if (now - self._cache_time).total_seconds() < 300 and self._cache.market_status == market_status:
                    return self._cache
            signals = []
            if market_status == "OPEN":
                signals.extend(self.intraday.scan(quick=quick))
            signals.extend(self.swing.scan(quick=quick))
            signals.extend(self.positional.scan(quick=quick))

            self._cache = ScanResult(
                signals=signals,
                scan_timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                market_status=market_status,
                total_signals=len(signals),
            )
            self._cache_time = now
            return self._cache

    def start_background_scan(self, market_status: str) -> None:
        with self._lock:
            if self._scanning or self._fresh_cache(market_status):
                return
            self._scanning = True

        def worker():
            try:
                self.run_full_scan(market_status)
            finally:
                with self._lock:
                    self._scanning = False

        t = threading.Thread(target=worker, daemon=True, name="signal-scan")
        t.start()


scanner = SignalScanner()