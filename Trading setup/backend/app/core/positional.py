import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from app.models.schemas import Signal
from app.data.market_data import market_data
from app.core.chart_analysis import chart_analyzer
from app.config import settings

logger = logging.getLogger(__name__)

CANDIDATE_LIMIT = 40
WMA_PERIOD = 30
MIN_WEEKS_ABOVE = 6


class Stage2BreakoutStrategy:
    def __init__(self):
        self.strategy_name = "Positional Stage 2 (30-Week WMA Support)"
        self.segment = "LONG-TERM"

    def scan(self, quick: bool = True) -> list[Signal]:
        quotes = market_data.get_stock_quotes(settings.NIFTY_200_SYMBOLS)
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
                    logger.warning("[positional] Error for %s: %s", symbol, e)
        return signals

    def _pick_candidates(self, quotes: dict) -> list[str]:
        scored = []
        for symbol, q in quotes.items():
            pct = q.get("change_pct")
            if pct is None or pct < -2.0 or pct > 3.0:
                continue
            scored.append((symbol, pct))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:CANDIDATE_LIMIT]]

    def _generate_signal(self, symbol: str, quotes: dict) -> Signal | None:
        d = chart_analyzer.get_daily_2y(symbol)
        if not d:
            return None
        df = pd.DataFrame({
            "date": pd.to_datetime(d["dates"]),
            "high": d["high"],
            "low": d["low"],
            "close": d["close"],
        }).set_index("date")

        wk = df.resample("W-FRI").agg({"close": "last", "high": "max", "low": "min"}).dropna()
        wk_closes = wk["close"].astype(float).tolist()
        wk_highs = wk["high"].astype(float).tolist()
        wk_lows = wk["low"].astype(float).tolist()
        if len(wk_closes) < WMA_PERIOD + 6:
            return None

        wma_series = [sum(wk_closes[max(0, i - WMA_PERIOD + 1):i + 1]) / len(wk_closes[max(0, i - WMA_PERIOD + 1):i + 1]) for i in range(len(wk_closes))]
        wma_now = wma_series[-1]
        wma_prev5 = wma_series[-6]
        wma_prev = wma_series[-2]

        growing = wma_now > wma_prev5
        cur = wk_closes[-1]
        prev_close = wk_closes[-2]
        above = cur > wma_now

        reclaim = prev_close < wma_prev and cur >= wma_now
        pullback = prev_close >= wma_prev and wk_lows[-1] <= wma_now * 1.03 and cur >= wma_now
        if not (above and growing and (reclaim or pullback)):
            return None

        recent_wma = wma_series[-12:]
        recent_closes = wk_closes[-12:]
        weeks_above = sum(1 for c, w in zip(recent_closes, recent_wma) if c > w)
        if weeks_above < MIN_WEEKS_ABOVE:
            return None

        atr_w = sum(wk_highs[i] - wk_lows[i] for i in range(len(wk_highs) - 14, len(wk_highs))) / 14
        slope_pct = ((wma_now / max(wma_prev5, 1)) - 1) * 100

        entry = (quotes.get(symbol) or {}).get("last") or cur
        sl = wma_now - 0.5 * atr_w
        t1 = entry * 1.25
        t2 = entry * 1.50
        upside = ((t1 - entry) / entry) * 100
        downside = ((entry - sl) / entry) * 100
        rr = round(upside / downside, 2) if downside > 0 else None

        slope_boost = int(slope_pct) if (slope_pct == slope_pct and slope_pct > 0) else 0
        confidence = min(70 + min(slope_boost, 4) * 2 + weeks_above, 90)
        if confidence < settings.MIN_SIGNAL_CONFIDENCE:
            return None

        setup = "Reclaim of 30-WK WMA" if reclaim else "Pullback holding 30-WK WMA"
        note = (
            f"{setup}: weekly close {cur:.2f} vs rising 30-WK WMA {wma_now:.2f} (slope {slope_pct:.2f}%/wk). "
            f"{weeks_above}/12 last weeks held above WMA. Stop below WMA support. Weekly TF \u2014 structure, not intraday signal."
        )

        return Signal(
            ticker=symbol, segment=self.segment,
            direction="BULLISH", action="BUY",
            entry_timestamp=f"Weekly Close: {datetime.now().strftime('%Y-%m-%d')}",
            entry_price=round(entry, 2),
            entry_range_low=round(max(entry * 0.99, wma_now), 2),
            entry_range_high=round(entry * 1.01, 2),
            target_1=round(t1, 2), target_2=round(t2, 2),
            stop_loss=round(sl, 2), exit_time="30-Week WMA Breach (weekly close below)",
            signal_date=datetime.now().strftime("%Y-%m-%d"),
            strategy_name=self.strategy_name, confidence=confidence,
            upside_pct=round(upside, 1), downside_pct=round(downside, 1),
            rr_ratio=rr, chart_note=note, current_price=round(entry, 2),
        )