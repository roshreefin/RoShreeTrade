import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.models.schemas import Signal
from app.data.market_data import market_data
from app.core.chart_analysis import chart_analyzer
from app.config import settings

logger = logging.getLogger(__name__)

DELAY_DISCLAIMER = (
    "This intraday signal is based on 15-minute delayed data (Yahoo Finance), not live tick quotes. "
    "Always verify the live price before entry and use a strict stop loss to avoid slippage losses."
)

CANDIDATE_LIMIT = 30
ENTRY_HOUR = 10
ENTRY_MINUTE = 15
EXIT_HOUR = 14
EXIT_MINUTE = 30


class MomentumStrategy:
    def __init__(self):
        self.strategy_name = "Intraday Momentum (RVOL + VWAP)"
        self.segment = "INTRADAY"

    def scan(self, quick: bool = True) -> list[Signal]:
        now = datetime.now()
        if now.hour < ENTRY_HOUR or (now.hour == ENTRY_HOUR and now.minute < ENTRY_MINUTE):
            return []
        if now.hour > EXIT_HOUR or (now.hour == EXIT_HOUR and now.minute > EXIT_MINUTE):
            return []

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
                    logger.warning("[momentum] Error for %s: %s", symbol, e)
        return signals

    def _pick_candidates(self, quotes: dict) -> list[str]:
        scored = []
        for symbol, q in quotes.items():
            pct = q.get("change_pct")
            if pct is None:
                continue
            scored.append((symbol, abs(pct)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:CANDIDATE_LIMIT]]

    def _generate_signal(self, symbol: str, quotes: dict) -> Signal | None:
        rows = chart_analyzer.get_intraday_15m(symbol)
        if not rows:
            return None

        by_day = {}
        for r in rows:
            by_day.setdefault(r["ts"].date(), []).append(r)
        days = sorted(by_day.keys())
        if len(days) < 2:
            return None
        today_bars = by_day[days[-1]]
        if len(today_bars) < 3:
            return None

        cum_pv = 0.0
        cum_v = 0.0
        for b in today_bars:
            tp = (b["high"] + b["low"] + b["close"]) / 3.0
            cum_pv += tp * b["volume"]
            cum_v += b["volume"]
        if cum_v <= 0:
            return None
        vwap = cum_pv / cum_v
        slot = len(today_bars)
        today_vol = sum(b["volume"] for b in today_bars)

        prior_slot_totals = []
        for d in days[:-1]:
            bars = by_day[d]
            if len(bars) >= slot:
                prior_slot_totals.append(sum(b["volume"] for b in bars[:slot]))
        if not prior_slot_totals:
            return None
        expected = sum(prior_slot_totals) / len(prior_slot_totals)
        rvol = today_vol / max(expected, 1.0)
        if rvol < 2.0:
            return None

        last_close = today_bars[-1]["close"]
        prev_close = today_bars[-2]["close"]
        last_low = today_bars[-1]["low"]
        last_high = today_bars[-1]["high"]

        long_reclaim = last_close > vwap and prev_close < vwap
        long_pullback = last_close <= vwap and last_close >= vwap * 0.995 and prev_close > vwap
        short_reclaim = last_close < vwap and prev_close > vwap
        short_pullback = last_close >= vwap and last_close <= vwap * 1.005 and prev_close < vwap

        if long_reclaim or long_pullback:
            direction = "BULLISH"
            action = "BUY"
            event = "VWAP Reclaim" if long_reclaim else "VWAP Pullback"
            entry = last_close
            stop = entry * 0.988
            t1 = entry * 1.008
            t2 = entry * 1.015
        elif short_reclaim or short_pullback:
            direction = "BEARISH"
            action = "SHORT SELL"
            event = "VWAP Breakdown" if short_reclaim else "VWAP Rally Reject"
            entry = last_close
            stop = entry * 1.012
            t1 = entry * 0.992
            t2 = entry * 0.985
        else:
            return None

        upside = abs((t1 - entry) / entry) * 100
        downside = abs((entry - stop) / entry) * 100
        rr = round(upside / downside, 2) if downside > 0 else None
        rvol_boost = int((rvol - 2.0) * 4) if (rvol == rvol and rvol > 2.0) else 0
        confidence = min(70 + rvol_boost + (6 if long_pullback or short_pullback else 4), 88)
        if confidence < settings.MIN_SIGNAL_CONFIDENCE:
            return None

        note = (
            f"{event}: RVOL {rvol:.1f}x, VWAP {vwap:.2f}, last {last_close:.2f}. "
            f"High relative volume with price action around VWAP. {DELAY_DISCLAIMER}"
        )

        _exit_label = f"{(EXIT_HOUR - 12) if EXIT_HOUR > 12 else EXIT_HOUR}:{EXIT_MINUTE:02d} PM"

        return Signal(
            ticker=symbol, segment=self.segment,
            direction=direction, action=action,
            entry_timestamp=datetime.now().strftime("%I:%M %p"),
            entry_price=round(entry, 2),
            entry_range_low=round(min(entry, last_low) * 0.998, 2),
            entry_range_high=round(max(entry, last_high) * 1.002, 2),
            target_1=round(t1, 2), target_2=round(t2, 2),
            stop_loss=round(stop, 2), exit_time=_exit_label,
            signal_date=datetime.now().strftime("%Y-%m-%d"),
            strategy_name=self.strategy_name, confidence=confidence,
            upside_pct=round(upside, 1), downside_pct=round(downside, 1),
            rr_ratio=rr, chart_note=note, current_price=round(entry, 2),
            disclaimer=DELAY_DISCLAIMER,
        )