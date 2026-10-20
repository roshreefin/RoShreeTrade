import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.models.schemas import Signal
from app.data.market_data import market_data
from app.core.chart_analysis import chart_analyzer
from app.config import settings

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 50
LOOKBACK = 60
CONTRACTION_MIN = 1.4
MAX_LATE_RANGE_PCT = 0.012


class VCPStrategy:
    def __init__(self):
        self.strategy_name = "Swing VCP (Volatility Contraction Breakout)"
        self.segment = "SWING"

    def scan(self, quick: bool = True) -> list[Signal]:
        quotes = market_data.get_stock_quotes(settings.NIFTY_500_SYMBOLS)
        candidates = self._pick_candidates(quotes)
        if not candidates:
            return []
        signals = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(self._generate_signal, symbol, quotes): symbol for symbol in candidates}
            for fut in as_completed(futures):
                symbol = futures[fut]
                try:
                    sig = fut.result()
                    if sig:
                        signals.append(sig)
                except Exception as e:
                    logger.warning("[swing] Error for %s: %s", symbol, e)
        return signals

    def _pick_candidates(self, quotes: dict) -> list[str]:
        scored = []
        for symbol, q in quotes.items():
            pct = q.get("change_pct")
            if pct is None or pct < 0.2:
                continue
            scored.append((symbol, pct))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:CANDIDATE_LIMIT]]

    def _generate_signal(self, symbol: str, quotes: dict) -> Signal | None:
        d = chart_analyzer.get_daily_2y(symbol)
        if not d:
            return None
        closes = d["close"]
        highs = d["high"]
        lows = d["low"]
        vols = d["volume"]
        n = len(closes)
        if n < 70:
            return None

        last = closes[-1]
        if last <= 0:
            return None

        sma50 = sum(closes[-50:]) / 50
        if last <= sma50:
            return None

        def avg_range(start, end):
            seg = range(start, end)
            if not seg:
                return 0.0
            return sum((highs[i] - lows[i]) / closes[i] for i in seg) / len(seg)

        early = avg_range(n - LOOKBACK + 10, n - LOOKBACK + 35) if n - LOOKBACK + 35 >= n - LOOKBACK + 10 else 0.0
        late = avg_range(n - 10, n)
        if late <= 0 or early <= 0:
            return None
        contraction = early / late
        late_pct = late * 100

        if contraction < CONTRACTION_MIN or late > MAX_LATE_RANGE_PCT:
            return None

        pivot_high = max(highs[n - 26:n - 1])
        base_low = min(lows[n - 26:n])
        if last <= pivot_high:
            return None

        avg_vol = sum(vols[n - 21:n - 1]) / 20
        vr = vols[-1] / max(avg_vol, 1) if avg_vol > 0 else 1.0
        if vr < 1.2:
            return None

        rng = pivot_high - base_low
        entry = last
        sl = base_low - 0.15 * rng
        t1 = pivot_high + 1.0 * rng
        t2 = pivot_high + 1.8 * rng
        upside = ((t1 - entry) / entry) * 100
        downside = ((entry - sl) / entry) * 100
        rr = round(upside / downside, 2) if downside > 0 else None

        conf_boost = int((contraction - CONTRACTION_MIN) * 12) if (contraction == contraction and contraction > 0) else 0
        confidence = min(70 + conf_boost + (6 if vr >= 2 else 2), 90)
        if confidence < settings.MIN_SIGNAL_CONFIDENCE:
            return None

        note = (
            f"VCP: {LOOKBACK}-session range compression {contraction:.1f}x (recent late-window range {late_pct:.2f}%), "
            f"tight base low {base_low:.2f}. Breakout above pivot {pivot_high:.2f} on {vr:.1f}x volume. "
            f"Daily EOD data (final closes) \u2014 enter on confirmed daily close, not intraday."
        )

        return Signal(
            ticker=symbol, segment=self.segment,
            direction="BULLISH", action="BUY",
            entry_timestamp=f"Daily Close: {datetime.now().strftime('%Y-%m-%d')}",
            entry_price=round(entry, 2),
            entry_range_low=round(entry * 0.995, 2),
            entry_range_high=round(entry * 1.005, 2),
            target_1=round(t1, 2), target_2=round(t2, 2),
            stop_loss=round(sl, 2), exit_time="Base Low Violation / Trailing 20-day EMA",
            signal_date=datetime.now().strftime("%Y-%m-%d"),
            strategy_name=self.strategy_name, confidence=confidence,
            upside_pct=round(upside, 1), downside_pct=round(downside, 1),
            rr_ratio=rr, chart_note=note, current_price=round(entry, 2),
        )