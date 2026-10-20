import time
import yfinance as yf
import numpy as np
from app.models.schemas import TechnicalAnalysis
from app.data.market_data import NSE_TO_YF

HISTORY_CACHE_TTL_SECONDS = 900
INTRADAY_CACHE_TTL_SECONDS = 300
DAILY_CACHE_TTL_SECONDS = 3600


class ChartAnalyzer:
    def __init__(self):
        self._history_cache = {}
        self._intraday_cache = {}
        self._daily_cache = {}
    def _calc_rsi(self, closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)

    def _calc_macd(self, closes: list[float]) -> tuple[str, float, float]:
        if len(closes) < 26:
            return ("NEEDS DATA", 0, 0)
        def ema(data, period):
            k = 2 / (period + 1)
            result = [data[0]]
            for i in range(1, len(data)):
                result.append(data[i] * k + result[-1] * (1 - k))
            return result
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
        signal_line = ema(macd_line[25:], 9) if len(macd_line) > 25 else [0]
        hist = macd_line[-1] - (signal_line[-1] if signal_line else 0)
        if macd_line[-1] > (signal_line[-1] if signal_line else 0) and macd_line[-2] <= (signal_line[-2] if len(signal_line) > 1 else 0):
            return ("BULLISH CROSSOVER", round(macd_line[-1], 2), round(hist, 2))
        elif macd_line[-1] < (signal_line[-1] if signal_line else 0) and macd_line[-2] >= (signal_line[-2] if len(signal_line) > 1 else 0):
            return ("BEARISH CROSSOVER", round(macd_line[-1], 2), round(hist, 2))
        elif macd_line[-1] > (signal_line[-1] if signal_line else 0):
            return ("BULLISH", round(macd_line[-1], 2), round(hist, 2))
        else:
            return ("BEARISH", round(macd_line[-1], 2), round(hist, 2))

    def _calc_support_resistance(self, closes: list[float], current: float) -> tuple[list[float], list[float]]:
        if len(closes) < 20:
            return ([round(current * 0.97, 2), round(current * 0.94, 2)],
                    [round(current * 1.03, 2), round(current * 1.06, 2)])
        recent = closes[-60:] if len(closes) >= 60 else closes
        lows = sorted(set(recent))[:3]
        highs = sorted(set(recent), reverse=True)[:3]
        support = sorted([round(l, 2) for l in lows if l < current], reverse=True)[:2]
        resistance = sorted([round(h, 2) for h in highs if h > current])[:2]
        if len(support) < 2:
            support.append(round(current * 0.95, 2))
        if len(resistance) < 2:
            resistance.append(round(current * 1.05, 2))
        return (support, resistance)

    def _get_history(self, yf_sym: str) -> tuple[list[float], list[float], float] | None:
        cached = self._history_cache.get(yf_sym)
        if cached:
            cached_at, cached_data = cached
            if time.time() - cached_at < HISTORY_CACHE_TTL_SECONDS:
                return cached_data

        try:
            t = yf.Ticker(yf_sym)
            hist = t.history(period="3mo", interval="1d")
            if hist is not None and len(hist) >= 5:
                hist = hist[hist["Close"].notna() & (hist["Close"] > 0)]
                if len(hist) < 5:
                    return None
                closes = hist["Close"].astype(float).tolist()
                volumes = hist["Volume"].fillna(0).astype(float).tolist()
                price = float(closes[-1])
                if price != price or price <= 0:
                    return None
                data = (closes, volumes, price)
                self._history_cache[yf_sym] = (time.time(), data)
                return data
        except Exception:
            pass
        return None

    def _get_fallback_price(self, yf_sym: str) -> float | None:
        try:
            fi = yf.Ticker(yf_sym).fast_info
            price = getattr(fi, "last_price", None) or getattr(fi, "previous_close", None)
            if price and float(price) > 0:
                return float(price)
        except Exception:
            pass
        return None

    def get_latest_and_prev(self, ticker: str) -> tuple[float, float, float, float] | None:
        yf_sym = NSE_TO_YF.get(ticker, ticker + ".NS")
        hist = self._get_history(yf_sym)
        if hist is None or len(hist[0]) < 2:
            return None
        closes = hist[0]
        return closes[-1], closes[-2], max(closes), min(closes)

    def get_intraday_15m(self, ticker: str) -> list[dict] | None:
        yf_sym = NSE_TO_YF.get(ticker, ticker + ".NS")
        cached = self._intraday_cache.get(yf_sym)
        if cached and time.time() - cached[0] < INTRADAY_CACHE_TTL_SECONDS:
            return cached[1]
        for attempt in range(3):
            try:
                hist = yf.Ticker(yf_sym).history(period="10d", interval="15m")
                if hist is None or len(hist) < 10:
                    return None
                rows = []
                for idx, row in hist.iterrows():
                    rows.append({
                        "ts": idx,
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row["Volume"] or 0),
                    })
                self._intraday_cache[yf_sym] = (time.time(), rows)
                return rows
            except Exception:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    return None
        return None

    def get_daily_2y(self, ticker: str) -> dict | None:
        yf_sym = NSE_TO_YF.get(ticker, ticker + ".NS")
        cached = self._daily_cache.get(yf_sym)
        if cached and time.time() - cached[0] < DAILY_CACHE_TTL_SECONDS:
            return cached[1]
        for attempt in range(3):
            try:
                hist = yf.Ticker(yf_sym).history(period="2y", interval="1d")
                if hist is None or len(hist) < 60:
                    return None
                hist = hist.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
                hist = hist[(hist["High"] > 0) & (hist["Low"] > 0) & (hist["Close"] > 0)]
                if len(hist) < 60:
                    return None
                data = {
                    "dates": [str(d.date()) if hasattr(d, "date") else str(d) for d in hist.index],
                    "open": hist["Open"].astype(float).tolist(),
                    "high": hist["High"].astype(float).tolist(),
                    "low": hist["Low"].astype(float).tolist(),
                    "close": hist["Close"].astype(float).tolist(),
                    "volume": hist["Volume"].fillna(0).astype(float).tolist(),
                }
                self._daily_cache[yf_sym] = (time.time(), data)
                return data
            except Exception:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1) + (yf_sym.__hash__() % 3) * 0.3)
                else:
                    return None
        return None

    def analyze(self, ticker: str) -> TechnicalAnalysis:
        yf_sym = NSE_TO_YF.get(ticker, ticker + ".NS")
        price = None
        closes = []
        volumes = []

        hist = self._get_history(yf_sym)
        if hist:
            closes, volumes, price = hist
        else:
            price = self._get_fallback_price(yf_sym)

        if not price:
            return TechnicalAnalysis(
                ticker=ticker, trend="NEUTRAL",
                pattern=None, recommendation="DATA UNAVAILABLE",
                confidence=0, data_available=False,
            )

        if len(closes) < 15:
            return TechnicalAnalysis(
                ticker=ticker, last_price=price, trend="NEUTRAL",
                pattern=None, recommendation="INSUFFICIENT HISTORY",
                confidence=0, data_available=False,
            )

        rsi = self._calc_rsi(closes) if len(closes) > 14 else 50.0
        macd_label, macd_val, macd_hist = self._calc_macd(closes)
        support, resistance = self._calc_support_resistance(closes, price)

        avg_vol = sum(volumes[-20:]) / max(len(volumes[-20:]), 1) if volumes else 1
        latest_vol = volumes[-1] if volumes else avg_vol
        vol_ratio = latest_vol / max(avg_vol, 1) if avg_vol > 0 else 1

        if vol_ratio > 1.5:
            vol_label = f"ABOVE AVG ({vol_ratio:.1f}x) — {'accumulation' if rsi > 50 else 'distribution'}"
        elif vol_ratio < 0.6:
            vol_label = f"BELOW AVG ({vol_ratio:.1f}x) — low participation"
        else:
            vol_label = f"AVERAGE ({vol_ratio:.1f}x)"

        if rsi > 60 and "BULLISH" in macd_label:
            trend = "BULLISH"
            rec = "BUY on dips — uptrend confirmed by RSI + MACD"
            conf = min(75 + int(vol_ratio * 5), 90)
            pat = "Stage 2 Breakout"
        elif rsi < 40 and "BEARISH" in macd_label:
            trend = "BEARISH"
            rec = "AVOID / SHORT on rally — downtrend confirmed"
            conf = min(70 + int(vol_ratio * 5), 85)
            pat = "Distribution Phase"
        elif rsi > 55:
            trend = "BULLISH"
            rec = "CAUTIOUS BUY — RSI positive but MACD unconfirmed"
            conf = 65
            pat = "Early Uptrend"
        elif rsi < 45:
            trend = "BEARISH"
            rec = "CAUTIOUS SHORT — RSI negative but MACD unconfirmed"
            conf = 65
            pat = "Early Downtrend"
        else:
            trend = "NEUTRAL"
            rec = "WAIT for confirmation — no clear trend"
            conf = 50
            pat = "Consolidation"

        return TechnicalAnalysis(
            ticker=ticker, last_price=round(price, 2), trend=trend,
            support=support, resistance=resistance,
            rsi=rsi, macd=macd_label, volume_analysis=vol_label,
            pattern=pat, recommendation=rec, confidence=conf,
        )


chart_analyzer = ChartAnalyzer()
