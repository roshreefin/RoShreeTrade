from datetime import datetime, timedelta
import time
import yfinance as yf

LIVE_DATA_ENABLED = True

QUOTE_CACHE_TTL_SECONDS = 30

INDIAN_MARKET_HOLIDAYS_2026 = [
    "2026-01-26", "2026-03-03", "2026-03-14", "2026-03-27",
    "2026-04-01", "2026-04-14", "2026-04-16", "2026-05-01",
    "2026-08-15", "2026-08-19", "2026-08-27", "2026-10-02",
    "2026-10-09", "2026-10-28", "2026-10-29", "2026-11-13",
    "2026-12-25",
]

NSE_TO_YF = {
    "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "HDFCBANK": "HDFCBANK.NS",
    "INFY": "INFY.NS", "ICICIBANK": "ICICIBANK.NS", "SBIN": "SBIN.NS",
    "LT": "LT.NS", "TATASTEEL": "TATASTEEL.NS", "BHARTIARTL": "BHARTIARTL.NS",
    "KOTAKBANK": "KOTAKBANK.NS", "TRENT": "TRENT.NS", "HAL": "HAL.NS",
    "BEL": "BEL.NS", "TITAN": "TITAN.NS", "M&M": "M&M.NS",
    "AXISBANK": "AXISBANK.NS", "MARUTI": "MARUTI.NS", "SUNPHARMA": "SUNPHARMA.NS",
    "BAJFINANCE": "BAJFINANCE.NS", "TATACONSUM": "TATACONSUM.NS",
    "PIDILITIND": "PIDILITIND.NS", "DIXON": "DIXON.NS", "PERSISTENT": "PERSISTENT.NS",
    "HINDUNILVR": "HINDUNILVR.NS", "NTPC": "NTPC.NS", "POWERGRID": "POWERGRID.NS",
    "SIEMENS": "SIEMENS.NS", "ABB": "ABB.NS",
}


def _get_market_status() -> str:
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return "WEEKEND"
    today_str = now.strftime("%Y-%m-%d")
    if today_str in INDIAN_MARKET_HOLIDAYS_2026:
        return "HOLIDAY"
    open_dt = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_dt = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < open_dt:
        return "PRE-MARKET"
    elif open_dt <= now <= close_dt:
        return "OPEN"
    elif close_dt < now <= close_dt + timedelta(hours=1):
        return "POST-MARKET"
    else:
        return "CLOSED"


class MarketDataProvider:
    def __init__(self):
        print("[yfinance] Live data enabled — no API key needed.")
        self._quote_cache = {}

    def get_stock_prices(self, symbols: list[str]) -> dict[str, float]:
        cached_at = self._quote_cache.get("_ts")
        if cached_at and time.time() - cached_at < QUOTE_CACHE_TTL_SECONDS:
            return self._quote_cache.get("prices", {})

        result = {}
        yf_symbols = [NSE_TO_YF.get(s, s + ".NS") for s in symbols]
        try:
            tickers = yf.Tickers(" ".join(yf_symbols))
            for nse_sym, yf_sym in zip(symbols, yf_symbols):
                try:
                    info = tickers.tickers[yf_sym].fast_info
                    price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                    if price and float(price) > 0:
                        result[nse_sym] = float(price)
                except Exception:
                    pass
        except Exception as e:
            print(f"[yfinance] Batch quote error: {e}")

        self._quote_cache = {"_ts": time.time(), "prices": result}
        return result

    def get_stock_price(self, symbol: str) -> float | None:
        prices = self.get_stock_prices([symbol])
        return prices.get(symbol)

    def get_stock_quotes(self, symbols: list[str]) -> dict[str, dict]:
        cached_at = self._quote_cache.get("_qts_ts")
        if cached_at and time.time() - cached_at < QUOTE_CACHE_TTL_SECONDS:
            return self._quote_cache.get("quotes", {})

        result = {}
        yf_symbols = [NSE_TO_YF.get(s, s + ".NS") for s in symbols]
        try:
            tickers = yf.Tickers(" ".join(yf_symbols))
            for nse_sym, yf_sym in zip(symbols, yf_symbols):
                try:
                    info = tickers.tickers[yf_sym].fast_info
                    last = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                    prev = getattr(info, "previous_close", None)
                    vol = getattr(info, "last_volume", None)
                    last = float(last) if last else None
                    prev = float(prev) if prev else None
                    pct = round((last - prev) / prev * 100, 2) if (last and prev and prev != 0) else None
                    if last and last > 0:
                        result[nse_sym] = {"last": last, "prev": prev, "change_pct": pct, "volume": vol}
                except Exception:
                    pass
        except Exception as e:
            print(f"[yfinance] Batch quote error: {e}")

        self._quote_cache = {"_qts_ts": time.time(), "quotes": result}
        return result

    def get_market_overview(self) -> dict:
        status = _get_market_status()
        nifty = None; nifty_chg = None; banknifty = None
        if LIVE_DATA_ENABLED:
            try:
                nifty_t = yf.Ticker("^NSEI")
                bn_t = yf.Ticker("^NSEBANK")
                nifty = getattr(nifty_t.fast_info, "last_price", None)
                banknifty = getattr(bn_t.fast_info, "last_price", None)
                if nifty is not None:
                    prev_nifty = getattr(nifty_t.fast_info, "previous_close", None)
                    if prev_nifty and float(prev_nifty) > 0:
                        nifty_chg = round(((float(nifty) - float(prev_nifty)) / float(prev_nifty)) * 100, 2)
            except Exception as e:
                print(f"[yfinance] Overview error: {e}")
        return {
            "nifty_50": nifty, "nifty_change_pct": nifty_chg,
            "bank_nifty": banknifty, "market_status": status,
            "advance_decline_ratio": "N/A",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


market_data = MarketDataProvider()
