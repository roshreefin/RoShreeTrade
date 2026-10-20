from fastapi import APIRouter, Query, Body
from fastapi.responses import JSONResponse
from datetime import datetime, time as dt_time
import time
from app.core.scanner import scanner
from app.data.market_data import market_data
from app.data.news_aggregator import news_aggregator
from app.data.fiidii import fiidii_provider
from app.core.breadth import market_breadth
from app.core.risk import risk_engine
from app.core.chart_analysis import chart_analyzer
from app.core.fundamental import fundamental_analyzer
from app.core import portfolio as portfolio_service
from app.config import settings
from app.models.schemas import ScanResult, PositionSizingRecommendation
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

SECTOR_ETFS = {
    "Nifty Bank": "^NSEBANK",
    "Nifty IT": "^CNXIT",
    "Nifty Pharma": "^CNXPHARMA",
    "Nifty Auto": "^CNXAUTO",
    "Nifty FMCG": "^CNXFMCG",
    "Nifty Energy": "^CNXENERGY",
    "Nifty Metal": "^CNXMETAL",
    "Nifty Realty": "^CNXREALTY",
    "Nifty Infra": "^CNXINFRA",
    "Nifty Media": "^CNXMEDIA",
}

router = APIRouter()


@router.get("/api/overview")
def get_market_overview():
    try:
        return market_data.get_market_overview()
    except Exception as e:
        logger.error("Failed to fetch market overview: %s", e)
        return {"error": str(e), "market_status": "CLOSED", "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/api/signals")
def get_signals(
    segment: str = Query(None, pattern="^(INTRADAY|SWING|LONG-TERM)?$"),
    direction: str = Query(None, pattern="^(BULLISH|BEARISH)?$"),
    action: str = Query(None, pattern="^(BUY|SHORT SELL)?$"),
):
    try:
        now = datetime.now()
        skip_intraday = now.time() > dt_time(14, 30)

        overview = market_data.get_market_overview()
        status = overview.get("market_status", "CLOSED")
        cached = scanner.get_cached(status)
        if cached is None:
            scanner.start_background_scan(status)
            return ScanResult(
                signals=[],
                scan_timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                market_status=status,
                total_signals=0,
                scanning=True,
            )

        signals = cached.signals
        if skip_intraday:
            signals = [s for s in signals if s.segment != "INTRADAY"]
        if segment:
            signals = [s for s in signals if s.segment == segment]
        if direction:
            signals = [s for s in signals if s.direction == direction]
        if action:
            signals = [s for s in signals if s.action == action]

        return ScanResult(
            signals=signals,
            scan_timestamp=cached.scan_timestamp,
            market_status=cached.market_status,
            total_signals=len(signals),
        )
    except Exception as e:
        logger.error("Failed to generate signals: %s", e)
        return ScanResult(
            signals=[],
            scan_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            market_status="CLOSED",
            total_signals=0,
        )


@router.get("/api/news")
async def get_news(limit: int = Query(20, ge=1, le=50)):
    try:
        news = await news_aggregator.fetch_all()
        return {"news": news[:limit], "total": len(news), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    except Exception as e:
        return {"news": [], "total": 0, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "error": str(e)}


@router.get("/api/chart-analysis")
def get_chart_analysis(ticker: str = Query(..., min_length=1, max_length=20)):
    try:
        result = chart_analyzer.analyze(ticker.upper())
        result.signal = scanner.get_signal_for(ticker.upper())
        return result
    except Exception as e:
        logger.error("Chart analysis failed for %s: %s", ticker, e)
        return {"error": str(e), "ticker": ticker.upper()}


@router.get("/api/fundamental")
def get_fundamental_analysis(ticker: str = Query(..., min_length=1, max_length=20)):
    try:
        return fundamental_analyzer.get_analysis(ticker.upper())
    except Exception as e:
        logger.error("Fundamental analysis failed for %s: %s", ticker, e)
        return {"ticker": ticker.upper(), "available": False, "source": "screener.in",
                "error": str(e), "disclaimer": "Data source: https://www.screener.in", 
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/api/position-size")
def calculate_position_size(
    entry_price: float = Query(...),
    stop_loss: float = Query(...),
    total_capital: float = Query(10_00_000, ge=1_000),
    risk_percentage: float = Query(0.01, ge=0.001, le=0.05),
):
    result = risk_engine.calculate_position_size(total_capital, entry_price, stop_loss, risk_percentage)
    return result


STOCK_UNIVERSES = {
    "50": settings.NIFTY_50_SYMBOLS,
    "200": settings.NIFTY_200_SYMBOLS,
    "500": settings.NIFTY_500_SYMBOLS,
}
STOCK_SORT_KEYS = {"ticker", "name", "last", "change_pct", "volume", "signal"}


@router.get("/api/stocks")
def get_stocks(
    universe: str = Query("500", pattern="^(50|200|500)$"),
    q: str = Query(None, max_length=40),
    sort_by: str = Query("change_pct", pattern="^(ticker|name|last|change_pct|volume|signal)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    signal: str = Query("any", pattern="^(any|yes|no)$"),
):
    try:
        symbols = STOCK_UNIVERSES.get(universe, settings.NIFTY_500_SYMBOLS)
        quotes = market_data.get_stock_quotes(symbols)
        signal_map = scanner.get_signal_map()
        query = (q or "").strip().upper()

        rows = []
        for sym in symbols:
            qd = quotes.get(sym) or {}
            name = settings.STOCK_NAMES.get(sym, "")
            sig = signal_map.get(sym)
            if query and query not in sym and query not in name.upper():
                continue
            if signal == "yes" and not sig:
                continue
            if signal == "no" and sig:
                continue
            rows.append({
                "ticker": sym,
                "name": name,
                "last": qd.get("last"),
                "previous_close": qd.get("prev"),
                "change_pct": qd.get("change_pct"),
                "volume": qd.get("volume"),
                "signal": sig,
            })

        if sort_by in STOCK_SORT_KEYS:
            is_num = sort_by in ("last", "change_pct", "volume")
            if is_num:
                rows.sort(key=lambda r, k=sort_by: (r.get(k) is None, r.get(k) if r.get(k) is not None else 0))
            else:
                rows.sort(key=lambda r, k=sort_by: str(r.get(k) or "").upper())
            if order == "desc":
                rows = list(reversed(rows))

        return {
            "universe": universe,
            "total": len(rows),
            "stocks": rows,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        logger.error("Failed to list stocks: %s", e)
        return {"universe": universe, "total": 0, "stocks": [], "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "error": str(e)}


def _enrich_portfolio(positions: list[dict]) -> dict:
    tickers = list(dict.fromkeys(p["ticker"] for p in positions))
    quotes = market_data.get_stock_quotes(tickers) if tickers else {}
    enriched = []
    total_invested = 0.0
    total_value = 0.0
    for p in positions:
        qd = quotes.get(p["ticker"]) or {}
        last = qd.get("last")
        invested = p["qty"] * p["avg_price"]
        value = p["qty"] * last if last else None
        pnl = (value - invested) if value is not None else None
        pnl_pct = ((last / p["avg_price"]) - 1) * 100 if last else None
        enriched.append({
            **p,
            "invested": round(invested, 2),
            "last_price": last,
            "current_value": round(value, 2) if value is not None else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "day_change_pct": qd.get("change_pct"),
        })
        total_invested += invested
        total_value += value or 0
    summary = {
        "positions_count": len(enriched),
        "total_invested": round(total_invested, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_value - total_invested, 2),
        "total_pnl_pct": round((total_value / total_invested - 1) * 100, 2) if total_invested else None,
    }
    return {"positions": enriched, "summary": summary, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/api/portfolio")
def get_portfolio():
    try:
        return _enrich_portfolio(portfolio_service.list_positions())
    except Exception as e:
        logger.error("Failed to read portfolio: %s", e)
        return {"positions": [], "summary": {}, "error": str(e), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@router.post("/api/portfolio")
def add_to_portfolio(payload: dict = Body(...)):
    position = portfolio_service.add_position(payload)
    if not position:
        return JSONResponse({"error": "Invalid position. Need ticker, qty > 0 and avg_price > 0."}, status_code=400)
    enriched = _enrich_portfolio([position])
    return enriched["positions"][0]


@router.patch("/api/portfolio/{position_id}")
def update_portfolio_position(position_id: str, payload: dict = Body(...)):
    position = portfolio_service.update_position(position_id, payload)
    if not position:
        return JSONResponse({"error": "Position not found."}, status_code=404)
    enriched = _enrich_portfolio([position])
    return enriched["positions"][0]


@router.delete("/api/portfolio/{position_id}")
def delete_portfolio_position(position_id: str):
    ok = portfolio_service.delete_position(position_id)
    if not ok:
        return JSONResponse({"error": "Position not found."}, status_code=404)
    return {"ok": True, "id": position_id}


SECTOR_CACHE_TTL_SECONDS = 60
_sector_cache = {"_ts": 0, "data": None}


@router.get("/api/sectors")
def get_sectors():
    now_ts = time.time()
    if _sector_cache["_ts"] and now_ts - _sector_cache["_ts"] < SECTOR_CACHE_TTL_SECONDS:
        return _sector_cache["data"]
    try:
        sectors = []
        for name, symbol in SECTOR_ETFS.items():
            try:
                ticker = yf.Ticker(symbol)
                fi = ticker.fast_info
                last = getattr(fi, "last_price", None) or getattr(fi, "previous_close", None)
                prev = getattr(fi, "previous_close", None)
                if not (last and prev):
                    hist = ticker.history(period="5d", interval="1d")
                    closes = hist["Close"].dropna().tolist()
                    if len(closes) >= 2:
                        last = float(closes[-1])
                        prev = float(closes[-2])
                if last and prev and float(prev) != 0:
                    last = float(last)
                    change = round(last - float(prev), 2)
                    change_pct = round((change / float(prev)) * 100, 2)
                else:
                    change = 0.0
                    change_pct = 0.0
                trend = "bullish" if change_pct > 0.5 else "bearish" if change_pct < -0.5 else "neutral"
                sectors.append({
                    "name": name,
                    "last": round(last, 1) if last else None,
                    "change": change,
                    "change_pct": change_pct,
                    "trend": trend,
                })
            except Exception as e:
                logger.warning("Failed to fetch data for %s (%s): %s", name, symbol, e)
                sectors.append({"name": name, "last": None, "change": 0.0, "change_pct": 0.0, "trend": "neutral"})

        if not sectors:
            return {"sectors": [], "note": "Sector data unavailable", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

        top = max(sectors, key=lambda s: s["change_pct"])
        bottom = min(sectors, key=lambda s: s["change_pct"])

        result = {
            "sectors": sectors,
            "top_sector": top["name"],
            "bottom_sector": bottom["name"],
            "source": "Yahoo Finance (live index quotes)",
            "note": "Values are Yahoo Finance live index quotes; small deviations from NSE India official figures are expected at any snapshot moment.",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _sector_cache.update({"_ts": time.time(), "data": result})
        return result
    except Exception as e:
        logger.error("Failed to fetch sector data: %s", e)
        return {"sectors": [], "note": "Sector data unavailable", "error": str(e), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/api/flows")
def get_flows():
    try:
        return fiidii_provider.fetch()
    except Exception as e:
        logger.error("Failed to fetch FII/DII flows: %s", e)
        return {
            "daily": [],
            "summary": None,
            "disclaimer": "Live FII/DII data sources are unreachable right now.",
            "source": None,
            "available": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


@router.get("/api/breadth")
def get_breadth():
    try:
        return market_breadth.compute()
    except Exception as e:
        logger.error("Failed to compute market breadth: %s", e)
        return {
            "advances": None,
            "declines": None,
            "unchanged": None,
            "total": None,
            "advance_decline_ratio": None,
            "breadth_status": "unavailable",
            "week52_high": None,
            "week52_low": None,
            "high_low_ratio": None,
            "available": False,
            "disclaimer": "Could not compute breadth — live quotes unreachable.",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


SEASONAL_CALENDAR = [
    {
        "month": "January", "month_num": 1, "season": "Winter",
        "events": ["New Year budget anticipation", "Q3 earnings season", "Union Budget pre-positions"],
        "themes": ["Budget plays — infrastructure, railways, defence, PSU", "Q3 results winners/losers", "Winter demand — power, coal"],
        "sectors_bullish": [
            {"name": "Infrastructure", "stocks": ["L&T", "IRCON", "RVNL"], "reason": "Budget capex expectations drive infra stocks higher ahead of Feb budget."},
            {"name": "Defence", "stocks": ["HAL", "BEL", "COCHINSHIP"], "reason": "Budget defence allocation expectations create buying interest."},
            {"name": "Power & Coal", "stocks": ["NTPC", "POWERGRID", "COALINDIA"], "reason": "Peak winter power demand boosts power generation and coal dispatch."},
        ],
        "sectors_bearish": [
            {"name": "Agrochemicals", "stocks": ["UPL", "DEEPAKNTR"], "reason": "Post-monsoon sowing season over. Agrochemical demand drops in winter."},
        ],
        "strategy": "Position for budget expectations in infra/defence by mid-January. Book profits before budget day if positions are up 10%+. Avoid chasing budget stocks after the event.",
    },
    {
        "month": "February", "month_num": 2, "season": "Winter / Budget",
        "events": ["Union Budget (Feb 1)", "Q3 results completion", "Global FII re-allocation"],
        "themes": ["Budget day volatility — buy-the-rumor, sell-the-fact", "Tax saving season starts", "Global risk-on/risk-off"],
        "sectors_bullish": [
            {"name": "Infrastructure", "stocks": ["L&T", "IRCON", "NCC"], "reason": "Budget usually announces highest capex allocation. Infra stocks rally on budget day."},
            {"name": "Railways", "stocks": ["IRFC", "RVNL", "RAILTEL"], "reason": "Railway budget allocation is a key catalyst. Stocks move 5-15% around budget."},
            {"name": "Banking", "stocks": ["HDFCBANK", "ICICIBANK"], "reason": "Budget tax breaks for home loans and credit growth benefits banking sector."},
        ],
        "sectors_bearish": [
            {"name": "Market (post-budget)", "stocks": ["NIFTY 50"], "reason": "Post-budget profit booking is common. Buy-the-rumor, sell-the-fact pattern in 70% of budgets."},
        ],
        "strategy": "Accumulate budget theme stocks by mid-January. Book 50% profits on budget day itself. If budget disappoints, wait for 2-3% correction to re-enter quality names. Start ELSS/80C tax-saving investments before March 31.",
    },
    {
        "month": "March", "month_num": 3, "season": "End of FY / Spring",
        "events": ["Financial year end", "Tax-saving deadline (Mar 31)", "Q4 results begin", "Window dressing by MFs"],
        "themes": ["Tax-saving urgency — ELSS, insurance, NPS", "MF portfolio rebalancing / window dressing", "Year-end provisioning and clean-up"],
        "sectors_bullish": [
            {"name": "ELSS / Mutual Funds", "stocks": ["HDFCAMC", "SBIMF"], "reason": "Last-minute 80C tax-saving inflows into ELSS funds boost AMC revenues and AUM."},
            {"name": "Insurance", "stocks": ["LIC", "HDFCLIFE"], "reason": "Year-end insurance buying for tax benefits. Strong Q4 premium collection."},
            {"name": "Banking", "stocks": ["HDFCBANK", "ICICIBANK"], "reason": "Year-end credit growth peaks. Balance sheet window dressing boosts deposits."},
        ],
        "sectors_bearish": [
            {"name": "High-beta mid-caps", "stocks": ["PERSISTENT", "DIXON"], "reason": "MF window dressing may lead to selling overvalued mid-caps to book gains before year-end."},
        ],
        "strategy": "Complete tax-saving investments before March 31. Don't chase ELSS in last week — premiums are high. Watch for MF rebalancing creating buying opportunities in quality small-caps after March-end. Prepare for Q4 earnings season.",
    },
    {
        "month": "April", "month_num": 4, "season": "New FY / Pre-Monsoon",
        "events": ["New financial year begins", "Q4 results peak", "Monsoon forecast by IMD (late April/May)"],
        "themes": ["Clean slate — fresh positions for new FY", "Q4 earnings-driven stock moves", "Pre-monsoon positioning begins"],
        "sectors_bullish": [
            {"name": "IT", "stocks": ["TCS", "INFY", "WIPRO"], "reason": "New FY brings fresh client budgets. Q4 deal wins drive stock reactions. Dollar revenue season."},
            {"name": "Pharma", "stocks": ["SUNPHARMA", "DRREDDY"], "reason": "New FY USFDA inspection cycle begins. Approval catalysts drive pharma stocks."},
            {"name": "Consumption", "stocks": ["HUL", "ITC", "NESTLEIND"], "reason": "Summer demand picks up. FMCG stocks benefit from hot weather product demand."},
        ],
        "sectors_bearish": [
            {"name": "Seasonal laggards", "stocks": ["Varies"], "reason": "Post-budget, post-tax-saving — market often goes through consolidation in April before monsoon clarity."},
        ],
        "strategy": "Q4 results will drive stock-specific action. Focus on companies with strong guidance for new FY. Start watching IMD monsoon forecasts — they become the key driver from May onwards. Build positions in summer/theme plays.",
    },
    {
        "month": "May", "month_num": 5, "season": "Pre-Monsoon / Summer Peak",
        "events": ["IMD monsoon forecast (late May)", "Summer peak demand", "US Fed meeting impact"],
        "themes": ["Monsoon forecast is THE key event — shapes rural India plays", "Summer demand peaks for cooling products", "Pre-election positioning (if election year)"],
        "sectors_bullish": [
            {"name": "Cooling & Appliances", "stocks": ["VOLTAS", "BLUESTARLT", "WHIRLPOOL"], "reason": "Peak summer demand. AC and refrigerator sales surge 30-40% in May-June."},
            {"name": "Beverages", "stocks": ["VARBEVERAGES", "BRITANNIA"], "reason": "Cold drinks and beverage demand peaks in summer heat."},
            {"name": "Power", "stocks": ["NTPC", "POWERGRID", "TATAPOWER"], "reason": "Peak summer power demand from cooling. Electricity consumption highest in May-June."},
        ],
        "sectors_bearish": [
            {"name": "Winter-specific", "stocks": ["VSTIND", "coal-related"], "reason": "Winter demand items lose relevance in peak summer."},
        ],
        "strategy": "IMD monsoon forecast (usually last week of May) is the biggest catalyst. If forecast is normal/above-normal, buy: fertilizers, seeds, irrigation, rural FMCG. If below-normal, buy: cooling stocks, power, and avoid rural plays. Summer theme trades work May-July.",
    },
    {
        "month": "June", "month_num": 6, "season": "Monsoon Begins",
        "events": ["Monsoon arrival (Kerala by June 1)", "RBI policy (bimonthly)", "Kharif sowing begins"],
        "themes": ["Monsoon progress becomes daily market driver", "Fertilizer and seed demand peaks", "Rural economy awakens"],
        "sectors_bullish": [
            {"name": "Fertilizers", "stocks": ["COROMANDEL", "CHAMBALFERT", "GSFC"], "reason": "Kharif sowing season. Fertilizer demand surges as monsoon arrives. Government subsidy payments boost revenues."},
            {"name": "Seeds & Pesticides", "stocks": ["UPL", "SUMICHEM", "BASF"], "reason": "Seed and pesticide demand peaks during kharif sowing. Farmers buy ahead of monsoon."},
            {"name": "Irrigation", "stocks": ["JINDALSAW", "PRINCE"], "reason": "Irrigation infrastructure demand rises with monsoon and government focus on water management."},
        ],
        "sectors_bearish": [
            {"name": "Cooling Appliances", "stocks": ["VOLTAS", "BLUESTARLT"], "reason": "AC and cooling demand drops sharply with monsoon arrival. Summer peak is over."},
        ],
        "strategy": "Fertilizer and seed stocks should be bought in early-mid June when sowing demand peaks. Don't chase after monsoon arrival is fully priced in. Watch IMD weekly monsoon progress reports — good monsoon = rural spending boost = FMCG rally.",
    },
    {
        "month": "July", "month_num": 7, "season": "Full Monsoon",
        "events": ["Peak monsoon rainfall", "AGM season begins", "Q1 results"],
        "themes": ["Monsoon progress tracking — weekly IMD updates move markets", "Rural demand picks up", "Q1 results of new FY"],
        "sectors_bullish": [
            {"name": "FMCG (Rural)", "stocks": ["HUL", "EMAMIL", "DABUR"], "reason": "Good monsoon drives rural income and FMCG consumption. Rural India contributes 35-40% of FMCG revenue."},
            {"name": "Two-Wheelers", "stocks": ["HEROMOTOCO", "BAJAJ-AUTO", "TVSMOTOR"], "reason": "Rural demand for two-wheelers rises with good monsoon and agricultural income."},
            {"name": "Tractors & Farm Equipment", "stocks": ["M&M", "ESCORTS"], "reason": "Good monsoon boosts tractor demand. M&M and Escorts benefit from rural mechanization."},
        ],
        "sectors_bearish": [
            {"name": "Sugar (if surplus)", "stocks": ["BALRAMPUR", "BAJAJHIND"], "reason": "Excess monsoon can lead to sugar surplus, pressuring sugar prices and stocks."},
        ],
        "strategy": "If monsoon is above-normal, add rural FMCG, two-wheelers, tractors. If monsoon is deficit, reduce rural plays and add defensive stocks. Q1 results in July confirm whether rural demand thesis is playing out. Use weekly IMD reports as trigger for adding/reducing positions.",
    },
    {
        "month": "August", "month_num": 8, "season": "Monsoon / Independence Day",
        "events": ["Independence Day (Aug 15)", "RBI policy", "Monsoon mid-season assessment"],
        "themes": ["Mid-monsoon assessment — market digests monsoon data", "RBI rate decision impacts market direction", "Low-volume holiday-shortened month"],
        "sectors_bullish": [
            {"name": "Banking", "stocks": ["HDFCBANK", "ICICIBANK", "SBIN"], "reason": "If RBI cuts rates or signals dovish stance, banking stocks rally. Credit growth data supports banks."},
            {"name": "Infrastructure", "stocks": ["L&T", "NCC"], "reason": "Monsoon completion allows construction activity to resume. Infra companies see order execution pick up."},
            {"name": "Textiles", "stocks": ["VARDHMAN", "WELSPUNIND"], "reason": "Cotton crop assessment from monsoon impacts textile raw material costs and margins."},
        ],
        "sectors_bearish": [
            {"name": "High-valuation stocks", "stocks": ["Various"], "reason": "August is typically a low-volume month. Thin liquidity can amplify any negative news."},
        ],
        "strategy": "August is relatively quiet. Use it to review monsoon performance and adjust rural/consumption positions. RBI policy is a key catalyst. Low volumes mean larger swings — use strict stop losses. Good time to accumulate quality stocks for festival season rally.",
    },
    {
        "month": "September", "month_num": 9, "season": "Monsoon Retreat / Pre-Festival",
        "events": ["Monsoon withdrawal begins", "Q1 results completion", "Pre-Dussehra/Diwali positioning"],
        "themes": ["Monsoon final assessment — determines rural spending outlook", "Pre-festival consumer demand anticipation", "FII re-allocation before year-end"],
        "sectors_bullish": [
            {"name": "Consumer Durables", "stocks": ["DIXON", "CLEAN"], "reason": "Festival season demand begins. Electronics and consumer goods orders surge ahead of Dussehra/Diwali."},
            {"name": "Jewelry", "stocks": ["TITAN", "KALYANKJIL"], "reason": "Wedding and festival season jewelry buying begins. Akshaya Tritiya sentiment lingers into festive quarter."},
            {"name": "Automobiles", "stocks": ["MARUTI", "M&M", "HEROMOTOCO"], "reason": "Festive season is the best quarter for auto sales. New model launches and offers drive demand."},
        ],
        "sectors_bearish": [
            {"name": "Fertilizers", "stocks": ["COROMANDEL", "GSFC"], "reason": "Sowing season is over. Fertilizer demand drops until next kharif season. Post-monsoon inventory correction."},
        ],
        "strategy": "Start building festival season plays in September — consumer durables, jewelry, autos. These stocks rally 10-20% from September to November. Book profits in fertilizer stocks as sowing ends. Watch for FII activity — they often reposition before year-end.",
    },
    {
        "month": "October", "month_num": 10, "season": "Festival Season Begins",
        "events": ["Dussehra", "Navratri", "Quarterly expiry", "FII activity peaks"],
        "themes": ["Festival consumer spending data is the key driver", "Market往往 gives strong returns Oct-Nov historically", "FII year-end positioning"],
        "sectors_bullish": [
            {"name": "Automobiles", "stocks": ["MARUTI", "TATAMOTORS", "HEROMOTOCO"], "reason": "Navratri is peak car-buying season. Auto companies register highest monthly sales in October."},
            {"name": "Consumer Electronics", "stocks": ["DIXON", "CLEAN"], "reason": "Festival season electronics demand peaks. TVs, smartphones, appliances see highest sales."},
            {"name": "Jewelry & Gold", "stocks": ["TITAN", "KALYANKJIL"], "reason": "Dhanteras and Diwali drive gold and jewelry buying. Best quarter for jewelry companies."},
        ],
        "sectors_bearish": [
            {"name": "Defensive (relative)", "stocks": ["IT", "PHARMA"], "reason": "During risk-on festival rally, defensive sectors underperform relatively. Money rotates to cyclicals."},
        ],
        "strategy": "October-November historically gives best market returns. Buy auto, consumer, jewelry stocks in early October. Dhanteras/Diwali gold buying supports jewelry stocks. Book partial profits before year-end. FII flows are typically strong in this period.",
    },
    {
        "month": "November", "month_num": 11, "season": "Peak Festival / Winter Begins",
        "events": ["Diwali", "Muhurat trading", "Q2 results", "Wedding season begins"],
        "themes": ["Diwali Muhurat trading — positive sentiment session", "Wedding season demand for jewelry, textiles, gifts", "Q2 results set market direction for winter"],
        "sectors_bullish": [
            {"name": "Jewelry", "stocks": ["TITAN", "KALYANKJIL", "PCJEWELLER"], "reason": "Peak wedding and Diwali jewelry buying. Best quarter for gold and diamond sales."},
            {"name": "Textiles & Apparel", "stocks": ["VARDHMAN", "WELSPUNIND"], "reason": "Wedding season drives demand for ethnic wear, fabrics, and home textiles."},
            {"name": "Media & Entertainment", "stocks": ["PVRINOX", "NETWORK18"], "reason": "Festival releases and entertainment spending peaks. Blockbuster movie releases drive box office."},
        ],
        "sectors_bearish": [
            {"name": "IT (relative)", "stocks": ["TCS", "INFY"], "reason": "Risk-on market prefers cyclicals. IT underperforms during festival rally despite strong fundamentals."},
        ],
        "strategy": "Diwali is peak sentiment. Book 30-50% profits from festival season plays. Wedding season sustains jewelry/textile demand into December. Q2 results in November set the tone for winter session. Watch for FII activity — they often book profits before year-end.",
    },
    {
        "month": "December", "month_num": 12, "season": "Year-End / Winter",
        "events": ["Year-end window dressing", "Christmas/New Year holidays", "FII year-end closes", "Global holiday-thinned volumes"],
        "themes": ["MF/Insurance year-end portfolio rebalancing", "Santa Claus rally (global)", "Low volumes amplify moves"],
        "sectors_bullish": [
            {"name": "Quality Large-Caps", "stocks": ["RELIANCE", "HDFCBANK", "TCS"], "reason": "Year-end MF rebalancing adds quality large-caps to portfolios. Window dressing creates buying."},
            {"name": "Insurance & AMC", "stocks": ["LIC", "HDFCLIFE", "HDFCAMC"], "reason": "Year-end insurance premium collection and tax-saving investment inflows boost AMC AUM."},
            {"name": "Winter Power", "stocks": ["NTPC", "POWERGRID"], "reason": "Peak winter power demand from heating. Electricity consumption rises."},
        ],
        "sectors_bearish": [
            {"name": "Agrochemicals", "stocks": ["UPL", "DEEPAKNTR"], "reason": "Rabi sowing is underway. Agrochemical demand is in off-season."},
        ],
        "strategy": "December is a low-volume month. Window dressing by MFs can push quality stocks higher. Use dips to accumulate for next year. Don't take large positions in thin markets. Plan next year's portfolio strategy. Tax-loss harvesting — sell losers for tax benefits before March 31.",
    },
]


@router.get("/api/seasonal")
def get_seasonal_calendar():
    now = datetime.now()
    current_month = now.month
    current = None
    upcoming = []
    past = []
    for entry in SEASONAL_CALENDAR:
        if entry["month_num"] == current_month:
            current = entry
        elif entry["month_num"] > current_month:
            upcoming.append(entry)
        else:
            past.append(entry)
    return {
        "current": current,
        "upcoming": upcoming[:3],
        "past": past[-2:],
        "all_months": SEASONAL_CALENDAR,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "1.0.0",
    }
