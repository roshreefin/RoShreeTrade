import os
import csv
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BACKEND_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

NIFTY_200_FALLBACK: list[str] = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "HCLTECH", "ASIANPAINT", "AXISBANK",
    "MARUTI", "SUNPHARMA", "TITAN", "BAJFINANCE", "NTPC", "ONGC", "POWERGRID",
    "ULTRACEMCO", "WIPRO", "ADANIPORTS", "NESTLEIND", "M&M", "TATASTEEL", "TECHM",
    "JSWSTEEL", "HDFCLIFE", "SBILIFE", "BAJAJFINSV", "DRREDDY", "COALINDIA",
    "BRITANNIA", "CIPLA", "GRASIM", "ADANIENT", "EICHERMOT", "DIVISLAB", "APOLLOHOSP",
    "HEROMOTOCO", "BPCL", "HINDALCO", "INDUSINDBK", "TATAMOTORS", "BAJAJ-AUTO",
    "SHREECEM", "HDFCAMC", "ICICIPRULI", "MARICO", "PIDILITIND", "AMBUJACEM",
    "DLF", "VEDL", "GAIL", "IOC", "BERGEPAINT", "ABFRL", "SIEMENS", "HAVELLS",
    "BEL", "BANKBARODA", "PAGEIND", "GODREJCP", "TRENT", "DABUR", "PEL", "COLPAL",
    "CADILAHC", "LUPIN", "AUROPHARMA", "MCDOWELL-N", "GODREJPROP", "SRTRANSFIN",
    "ICICIGI", "SBICARD", "ZOMATO", "POLYCAB", "INDUSTOWER", "JUBLFOOD", "BANDHANBNK",
    "CONCOR", "TORNTPHARM", "NAUKRI", "MUTHOOTFIN", "TIINDIA", "PERSISTENT",
    "LTTS", "KPITTECH", "INOXLEISUR", "HINDCOPPER", "NATIONALUM", "IRCTC", "HAL",
    "BHEL", "IDEA", "YESBANK", "PNB", "JINDALSTEL", "SAIL", "TVSMOTOR", "ASHOKLEY",
    "MOTHERSUMI", "EXIDEIND", "AMARAJABAT", "MRF", "APOLLOTYRE", "TATACONSUM",
    "VBL", "GODREJAGRO", "COROMANDEL", "UPL", "PIIND", "ALKEM", "TORNTPOWER",
    "ADANIGREEN", "ADANITRANS", "TATAELXSI", "MINDTREE", "COFORGE",
    "LTI", "LICHSGFIN", "M&MFIN", "CHOLAFIN", "BAJAJHOLD", "IDFCFIRSTB",
    "RBLBANK", "FEDERALBNK", "CUB", "AUBANK", "HOMEFIRST", "INDIANB", "CANBK"
]


def _load_nifty_csv(filename: str) -> tuple[list[str], dict[str, str]] | None:
    path = BACKEND_DATA_DIR / filename
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            symbols: list[str] = []
            names: dict[str, str] = {}
            for row in reader:
                sym = row.get("Symbol", "").strip()
                isin = row.get("ISIN Code", "").strip().upper()
                if not sym:
                    continue
                if "DUMMY" in sym.upper() or isin.startswith("DUM"):
                    continue
                symbols.append(sym)
                name = row.get("Company Name", "").strip()
                if name and sym not in names:
                    names[sym] = name
            return symbols, names
    except Exception:
        return None


def _load_nifty_symbols(filename: str) -> list[str] | None:
    loaded = _load_nifty_csv(filename)
    return loaded[0] if loaded else None


def _load_nifty_names(filename: str) -> dict[str, str]:
    loaded = _load_nifty_csv(filename)
    return loaded[1] if loaded else {}


class Settings:
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_ACCESS_TOKEN: str = os.getenv("KITE_ACCESS_TOKEN", "")
    USE_YFINANCE_FALLBACK: bool = os.getenv("USE_YFINANCE_FALLBACK", "true").lower() == "true"

    MIN_SIGNAL_CONFIDENCE: int = int(os.getenv("MIN_SIGNAL_CONFIDENCE", "70"))

    SCAN_INTERVAL_MINUTES: int = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))
    MARKET_OPEN_HOUR: int = int(os.getenv("MARKET_OPEN_HOUR", "9"))
    MARKET_OPEN_MINUTE: int = int(os.getenv("MARKET_OPEN_MINUTE", "15"))
    MARKET_CLOSE_HOUR: int = int(os.getenv("MARKET_CLOSE_HOUR", "15"))
    MARKET_CLOSE_MINUTE: int = int(os.getenv("MARKET_CLOSE_MINUTE", "30"))

    NIFTY_50_SYMBOLS: list[str] = _load_nifty_symbols("ind_nifty50list.csv") or NIFTY_200_FALLBACK[:50]
    NIFTY_200_SYMBOLS: list[str] = _load_nifty_symbols("ind_nifty200list.csv") or NIFTY_200_FALLBACK
    NIFTY_500_SYMBOLS: list[str] = _load_nifty_symbols("ind_nifty500list.csv") or NIFTY_200_FALLBACK

    STOCK_NAMES: dict[str, str] = _load_nifty_names("ind_nifty50list.csv") | _load_nifty_names("ind_nifty200list.csv") | _load_nifty_names("ind_nifty500list.csv")

    STAGE2_SECTORS: list[str] = [
        "DEFENSE", "ENERGY", "INFRASTRUCTURE", "EMS", "RENEWABLE",
        "IT", "PHARMA", "BANKING", "AUTO", "FMCG"
    ]


settings = Settings()
