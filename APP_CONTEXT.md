# Equity Signal Engine — Full App Context

## Project Overview
Automated buy/sell signal generation for NSE Cash (Equity) segment with 3 strategies:
1. **Intraday Momentum — RVOL + VWAP** (Intraday, Nifty 200, active 10:15 AM – 2:30 PM, 15-min delayed data with disclaimer on each card)
2. **Volatility Contraction Pattern (VCP)** (Swing, Nifty 500, Daily TF — range contraction → breakout above pivot on volume)
3. **Positional Stage 2 — 30-Week WMA Support** (Long-Term, Nifty 200, Weekly TF — reclaim/pullback of rising WMA)

Stack: FastAPI + yfinance → Vanilla JS frontend (dark theme, no build step)

Constituent universes come from official NSE archives CSVs (`backend/data/ind_nifty*list.csv`) for Nifty 50 / 200 / 500 (500 rows after filtering NSE's own **DUMMYHEG** placeholder row), with a hardcoded 134-symbol fallback if the files are missing.

---

## Directory Structure
```
Trading setup/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app, lifespan, static mount, routes
│   │   ├── config.py               # Settings, symbols, market hours
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes.py           # All /api/* endpoints (incl. stocks screener + portfolio)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── scanner.py          # SignalScanner orchestrates 3 strategies (300s cache; get_signal_for/get_signal_map)
│   │   │   ├── momentum.py         # MomentumStrategy (RVOL>2 + VWAP reclaim/pullback, 15-min delayed)
│   │   │   ├── swing.py            # VCPStrategy (real Volatility Contraction → breakout)
│   │   │   ├── positional.py       # Stage2BreakoutStrategy
│   │   │   ├── portfolio.py        # PortfolioStore — JSON-backed holdings CRUD (thread-safe)
│   │   │   ├── chart_analysis.py   # ChartAnalyzer (RSI, MACD, S/R, Volume, Trend + 15m/daily fetchers)
│   │   │   ├── breadth.py          # MarketBreadth (real NIFTY-200 advance/decline)
│   │   │   └── risk.py             # RiskEngine (position sizing, ATR stops)
│   │   ├── data/
│   │   │   ├── __init__.py
│   │   │   ├── market_data.py      # MarketDataProvider (yfinance wrapper, cached; get_stock_quotes)
│   │   │   ├── fiidii.py           # FiiDiiProvider (best-effort NSE/MoneyControl scraper)
│   │   │   └── news_aggregator.py  # NewsAggregator (RSS + NLP tagging, 726 lines)
│   │   └── models/
│   │       ├── __init__.py
│   │       └── schemas.py          # Pydantic models (Signal, ScanResult, etc.)
│   ├── requirements.txt            # 13 dependencies
│   ├── .env                        # KITE_API_KEY, KITE_ACCESS_TOKEN, USE_YFINANCE_FALLBACK
│   └── .env.example
│   ├── backend/data/               # Official NSE constituents (ind_nifty50/200/500list.csv) + portfolio.json (auto-created)
├── frontend/
│   ├── index.html                  # Dashboard (signals, overview, calculator) — cards clickable → chart
│   ├── chart.html                  # Technical analysis page + Live Signals dropdown
│   ├── news.html                   # News feed with impact analysis
│   ├── journal.html                # Trade journal with stats
│   ├── stocks.html                 # Stock screener (Nifty 50/200/500 tabs, search, sort, signal filter)
│   ├── portfolio.html              # Live mark-to-market portfolio manager
│   ├── sectors.html                # Sector rotation
│   ├── flows.html                  # FII/DII flows
│   ├── breadth.html                # Market breadth
│   ├── seasonal.html               # Seasonal calendar
│   ├── css/style.css               # Dark theme, CSS variables
│   └── js/app.js                   # All page logic
├── README.md
├── start.bat                        # Launches backend
├── APP_CONTEXT.md
└── .gitignore
```

---

## Backend Details

### main.py (80 lines)
- FastAPI with lifespan for APScheduler
- Scheduler runs `scheduled_scan()` every `SCAN_INTERVAL_MINUTES` (default 15)
- Mounts `/static` → `frontend/` directory
- Routes for 10 HTML pages via `page_map` (incl. `/stocks`, `/portfolio`)
- Runs on `uvicorn` at `0.0.0.0:8000`

### config.py (~70 lines)
- `Settings` class with env vars: KITE_API_KEY, KITE_ACCESS_TOKEN, USE_YFINANCE_FALLBACK, MIN_SIGNAL_CONFIDENCE, SCAN_INTERVAL_MINUTES, market hours
- `MIN_SIGNAL_CONFIDENCE` (default 70) — only confirmed setups qualify as signals; "CAUTIOUS BUY" (conf 65) is excluded so dashboard never contradicts the chart page
- `NIFTY_50_SYMBOLS` (50 symbols) — screener tab
- `NIFTY_200_SYMBOLS` (200 symbols) — Intraday + Positional universe
- `NIFTY_500_SYMBOLS` (500 symbols, after removing NSE's DUMMYHEG placeholder row) — VCP/Swing universe + screener
- `STOCK_NAMES` (ticker → company name, built from the Nifty 500 CSV)
- All universes loaded via `_load_nifty_csv()` from official NSE archives CSVs, with fallback to `NIFTY_200_FALLBACK` (134 hardcoded) when files are absent
- `STAGE2_SECTORS` (10 sectors)

### api/routes.py (~405 lines) — Key Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/overview` | Market status, Nifty, Bank Nifty, last_updated |
| `GET /api/signals` | Filtered signals (segment, direction, action) |
| `GET /api/news` | Aggregated news with impact analysis (limit 20) |
| `GET /api/chart-analysis?ticker=` | Technical analysis for symbol (+ attached `signal` plan when the ticker has a live cached signal) |
| `GET /api/stocks` | Stock screener — universe `50`/`200`/`500`, `q` search, sort_by ticker/name/last/change_pct/volume/signal, order asc/desc, signal any/yes/no |
| `GET /api/portfolio` | Enriched holdings (invested, LTP, current value, P&L, P&L%, summary totals) |
| `POST /api/portfolio` | Add holding (ticker, qty, avg_price, optional stop_loss/buy_date/segment/note) |
| `PATCH /api/portfolio/{id}` | Update holding (partial: qty, avg_price, stop_loss, segment, note) |
| `DELETE /api/portfolio/{id}` | Remove holding |
| `GET /api/position-size` | Position sizing calculator |
| `GET /api/sectors` | 10 sector indices — last value + abs change + %, 60s cache |
| `GET /api/flows` | FII/DII flows — best-effort scraper (NSE, MoneyControl); falls back to "unavailable" when unreachable |
| `GET /api/breadth` | Market breadth — REAL advance/decline computed from NIFTY-200 universe (60s cache) |
| `GET /api/seasonal` | 12-month seasonal calendar |
| `GET /api/health` | Health check |

### core/scanner.py (38 lines)
- `SignalScanner` class with 3 strategy instances (MomentumStrategy, VCPStrategy, Stage2BreakoutStrategy)
- `run_full_scan(market_status, quick=True)` → returns `ScanResult`
- 300-second in-memory cache keyed by market_status (limits yfinance load to ~1 heavy scan per 5 min)
- `get_signal_for(ticker)` / `get_signal_map()` — expose the cached scan result for chart-plan / screener badges

### core/portfolio.py
- `PortfolioStore` — CRUD over `backend/data/portfolio.json` (threading.Lock, auto-creates file)
- Fields: id, ticker, qty, avg_price, buy_date, segment (INTRADAY/SWING/LONG-TERM/MISC), stop_loss, note, created_at
- No dummy data; live mark-to-market applied in routes via `get_stock_quotes`

### core/momentum.py (165 lines)
- `MomentumStrategy` — Intraday Momentum (RVOL + VWAP)
- Universe: `settings.NIFTY_200_SYMBOLS` (200), pre-filtered to top 30 |day change| movers via `get_stock_quotes`
- Active only 10:15–14:30 (high-liquidity window)
- RVOL: today's cumulative 15m volume vs average same-slot volume of prior ~9 sessions; must be ≥ 2.0x
- VWAP: today's volume-weighted avg price of (H+L+C)/3; long on VWAP reclaim (prev<vwap, last>vwap) or pullback near VWAP (≤ +0.5%, prev>vwap); short mirror
- Entry = last delayed close; SL ±1.2%; T1 +0.8%, T2 +1.5%; confidence 70–88
- Every signal carries `disclaimer` — data is 15-min delayed (Yahoo), verify live price before entry; rendered prominently under intraday cards
- Data via `chart_analyzer.get_intraday_15m()` (10d/15m bars, 300s cache)

### core/swing.py (150 lines) — REAL VCP
- `VCPStrategy` — Volatility Contraction Pattern (Daily TF, Nifty 500)
- Universe: `settings.NIFTY_500_SYMBOLS` (501), pre-filtered to top 50 positive movers
- Uses `chart_analyzer.get_daily_2y()` (2y daily, 3600s cache) for every candidate
- Conditions: close > SMA50 (Stage-1 uptrend context); avg daily range% of [n-50,n-25) ÷ [n-10,n) ≥ 1.4 AND recent 10-session range ≤ 1.2%; breakout close above 25-session pivot high on volume ≥ 1.2× its 20-day avg
- Targets = pivot + 1.0× / 1.8× base range; stop below base low; confidence 70–90
- Long only, confirmed on daily close (never intraday)

### core/positional.py (150 lines) — REAL Stage 2 (Weekly TF, Nifty 200)
- `Stage2BreakoutStrategy`
- Universe: `settings.NIFTY_200_SYMBOLS` (200), pre-filtered to top 40 movers in [-2%, +3%]
- Daily data resampled to weekly (W-FRI) via pandas from `get_daily_2y()`
- Conditions: weekly close above a RISING 30-week WMA (now > 5 weeks ago); reclaim (prev week < WMA, this week ≥ WMA) or pullback (low touched ≤ 1.03×WMA, held ≥ WMA); ≥ 6 of last 12 weeks above their WMA
- Entry = current quote; SL below WMA (− 0.5× weekly ATR); targets +25%/+50%; confidence 70–90
- Long only, weekly structure — tactical entry on dip back toward WMA

### core/chart_analysis.py (215 lines)
- `ChartAnalyzer.analyze(ticker)` → `TechnicalAnalysis`
- Fetches 3mo daily data from yfinance with 15-min in-memory cache (900s)
- Calculates: RSI(14), MACD(12,26,9), Support/Resistance (60-day unique levels), Volume ratio (20-day avg)
- Trend classification: BULLISH/BEARISH/NEUTRAL with confidence 50-90
- Pattern labels: "Stage 2 Breakout", "Distribution Phase", "Early Uptrend", "Early Downtrend", "Consolidation"
- No dummy fallback: missing/insufficient data → `data_available=False`, "DATA UNAVAILABLE"/"INSUFFICIENT HISTORY"
- `get_latest_and_prev(ticker)` — public helper reusing the history cache (used by breadth)
- `get_intraday_15m(ticker)` — 10d/15m bars, 300s cache (used by momentum)
- `get_daily_2y(ticker)` — 2y daily bars, 3600s cache, shared by swing + positional

### core/breadth.py (85 lines)
- `MarketBreadth.compute()` → real breadth from NIFTY-200 universe
- Advances/declines/unchanged = last close vs previous close per symbol (via cached history)
- Ratio, breadth_status (strong/mixed/weak), 3-month highs/lows, 60s cache
- Returns `available: false` only if <50 symbols have live data

### data/fiidii.py (150 lines)
- `FiiDiiProvider.fetch()` → best-effort FII/DII daily figures (Rs crore)
- Sources tried in order: NSE India `fiidiiTradeReact` API (session warm-up), MoneyControl `fiidii_combined.json`
- Defensive JSON parsing, 15-min cache, never raises — falls back to `available: false`
- From the user's network both sources currently time out/503, so the page shows the live "unavailable" state and self-heals if they become reachable

### core/risk.py (68 lines)
- `RiskEngine`
- `calculate_atr_stop(entry, atr, multiplier=1.5)`
- `calculate_position_size(capital, entry, stop, risk_pct=0.01)` → `PositionSizingRecommendation`
- `format_signal_message(signal, capital)` → formatted Telegram-ready message

### data/market_data.py (135 lines)
- `MarketDataProvider`
- `_get_market_status()` → OPEN/CLOSED/PRE-MARKET/POST-MARKET/WEEKEND/HOLIDAY (uses 2026 holidays)
- `get_stock_prices(symbols)` → batch yfinance quotes via `NSE_TO_YF` mapping, 30s cache
- `get_stock_quotes(symbols)` → last/prev/change_pct/volume per symbol (fast_info batch, 60s cache) — used to pre-filter candidates across 200/500-symbol universes before heavy history fetches
- `get_market_overview()` → Nifty, Bank Nifty, status
- `LIVE_DATA_ENABLED = True`

### data/news_aggregator.py (726 lines)
- `NewsAggregator` with `fetch_all()` → list of `NewsItem`
- 5 Google News RSS feeds (Markets, FII/DII, Index, Earnings, RBI)
- Keyword detection: 28 sectors, 57 stock patterns, 22 event types
- Sentiment analysis (positive/negative/neutral)
- Impact generation: prediction, caution, do's, don'ts per event/sector
- Deduplication by title, sorted by date desc

### models/schemas.py (95 lines)
```python
class Signal(BaseModel):
    ticker, segment, direction, action, entry_timestamp, entry_price,
    entry_range_low, entry_range_high, target_1, target_2, stop_loss,
    exit_time, signal_date, confidence, strategy_name, is_active,
    upside_pct, downside_pct, rr_ratio, chart_note, current_price, disclaimer

class PositionSizingRecommendation(BaseModel): ...
class NewsItem(BaseModel): ...
class MarketOverview(BaseModel): ...
class ScanResult(BaseModel): signals, scan_timestamp, market_status, total_signals
class TechnicalAnalysis(BaseModel): ticker, last_price, trend, support, resistance, rsi, macd, volume_analysis, pattern, recommendation, confidence, data_available, signal (Optional[dict] — live plan, set by routes when the ticker holds a cached signal)
```

---

## Frontend Details

### index.html (119 lines) — Dashboard
- Market overview cards (Nifty, Nifty Change, Bank Nifty, Status)
- Signal tabs: All / Intraday / Swing / Long-Term
- Manual "Scan" button + auto-refresh 5 min
- Position Size Calculator (entry, SL, capital, risk%)
- Loads `static/js/app.js`

### chart.html — Technical Analyzer
- Ticker input → fetches `/api/chart-analysis`; supports `?ticker=` URL param (auto-analyze from dashboard/stocks clicks)
- **Live Signals dropdown**: lists cached scan signals; selecting one opens that symbol's analysis
- When the analyzed ticker has a live signal, the **signal plan card** (segment, action, entry, targets, stop, R:R, confidence, note, disclaimer) renders above the technicals

### news.html — News Feed
- Renders news cards with: title, source, date, sentiment, sector, affected stocks (clickable → chart)
- Impact: Prediction, Caution, Do's, Don'ts
- Bookmark toggle (localStorage), filter bookmarks

### journal.html — Trade Journal
- Form: date, ticker, direction (BUY/SHORT), qty, entry, exit, result (WIN/LOSS), R:R, notes
- Stats: total, wins, losses, win%, net P&L, avg R:R
- History table with P&L per trade
- localStorage persistence (`journal_trades`)

### sectors.html — Sector Rotation
- 10 sector indices via yfinance (^NSEBANK, ^CNXIT, etc.)
- Card shows `Nifty IT 28582.1 | -280.55 | -0.97%` (value | abs change | %), trend badge, top/bottom highlight
- 60s backend cache; source noted on page (Yahoo live quotes; may differ fractionally from NSE India's own site at a given snapshot)

### flows.html — FII/DII Flows
- Fetches `/api/flows`; live source labels + disclaimer; "data unavailable" state when sources unreachable (no simulated bars)

### breadth.html — Market Breadth
- Fetches `/api/breadth`; real NIFTY-200 advances/declines/unchanged + 3-mo highs/lows + scope tag; "unavailable" only when <50 symbols have data

### seasonal.html — Seasonal Calendar
- 12-month calendar (SEASONAL_CALENDAR in routes.py)
- Current month highlighted, upcoming/past
- Events, themes, bullish/bearish sectors with stocks & reasons, strategy

### css/style.css (605 lines)
- CSS custom properties (dark theme: #0a0e17 bg, #1a2332 cards)
- Inter font, responsive grid, animations
- Signal cards with left border color (green/red)
- Insight bar with R:R gauge
- Confidence bars, badges, loading spinners

### stocks.html — Stock Screener
- Tabs Nifty 50 / 200 / 500; search (ticker/company); sortable columns (ticker, last, day %, volume); signal filter (any/yes/no)
- Live price + change + volume per symbol from `get_stock_quotes`; live-signal badge from scanner cache
- Clicking a row opens `/chart?ticker=...`

### portfolio.html — Portfolio Manager
- Add holding form (ticker, qty, avg price, stop, buy date, segment); quick-add via "+ Add" button on dashboard signal cards
- Live mark-to-market: invested, LTP, current value, P&L (₹ / %), summary cards (holdings, invested, value, P&L)
- Backend-persisted (`backend/data/portfolio.json`), auto-refresh 60s; edit (qty/avg) and delete per row

### js/app.js (id-based cross-checked against all pages)
- `fetchAPI()` with 15s timeout + AbortController
- `renderOverview()`, `loadOverview()` (60s interval)
- `loadSignals()` with tab filtering
- `renderSignalCard()` with insight bar, confidence bar — renders `chart_note` and, when present, a highlighted `disclaimer` (amber warning) below intraday cards for the 15-min delay
- `loadChartAnalysis()`, `initChartScanner()`, `initChartSignals()`, `signalPlanHTML()`
- `loadStocks()` / `stockSortBy()` — screener tabs, debounced search, sortable headers
- `loadPortfolio()` / `addPosition()` / `editPosition()` / `deletePosition()` — live P&L summary + CRUD
- `fetchAPI_JSON()` (POST/PATCH/DELETE helper), `escapeHtml()`, `buttonAdd()` (quick portfolio add)
- `loadNews()`, `renderNewsList()`, bookmark delegation
- `initCalculator()` (real-time position sizing)
- `initTabs()`, `initDropdown()`
- `renderJournal()`, `addTrade()`, `clearJournal()`
- `loadSectors()`, `loadFlows()`, `loadBreadth()`
- Page detection via `getPage()`, auto-init on DOMContentLoaded
- `data_available: false` handling for chart analysis, flows, breadth ("Data Unavailable" empty states)

---

## Data Flow

```
User opens http://localhost:8000
    ↓
FastAPI serves index.html (mounted static)
    ↓
JS loads → loadOverview() → /api/overview → MarketDataProvider.get_market_overview()
    ↓
JS loads → loadSignals() → /api/signals → SignalScanner.run_full_scan()
    ↓
Scanner → Momentum (OPEN only) + VCP (Nifty 500) + Positional (Nifty 200) .scan()
    ↓
Each strategy → get_stock_quotes() → yfinance fast_info batch → pre-filter to ≤50 candidates
    ↓
Momentum → get_intraday_15m() bars → RVOL/VWAP logic (15-min delayed, disclaimer on card)
VCP/Positional → get_daily_2y() daily bars (positional resamples weekly) → VCP/weekly-WMA logic
    ↓
Strategy builds Signal with targets, stop-loss, R:R, chart_note (+ disclaimer for intraday)
    ↓
ScanResult returned (300s scanner cache + 60s quote cache + 3600s daily cache) → JSON → JS renders signal cards
```

---

## Key Configurations
- **Scan Interval**: 15 min (env: `SCAN_INTERVAL_MINUTES`); scanner in-memory cache 300s
- **Min Signal Confidence**: 70 (env: `MIN_SIGNAL_CONFIDENCE`) — excludes "CAUTIOUS BUY/Early Uptrend" setups
- **Market Hours**: 9:15–15:30 IST (env: `MARKET_OPEN_HOUR/MINUTE`, `MARKET_CLOSE_HOUR/MINUTE`)
- **Intraday Active**: 10:15–14:30, candidates = top 30 movers of Nifty 200, RVOL≥2 + VWAP setup
- **Swing (VCP)**: Nifty 500 top 50 movers, contraction ≥1.4x + late-range ≤1.2%, pivot breakout on ≥1.2x volume
- **Positional**: Nifty 200 top 40 movers in [-2,+3]%, weekly close vs rising 30-WK WMA (reclaim/pullback)
- **Risk Model**: 1% capital per trade (adjustable in calculator)
- **Cache TTLs**: quotes 30s, stockquotes/sector/breadth 60s, intraday-15m 300s, scanner 300s, daily-2y 3600s, chart history 900s, FII/DII 900s
- **News Limit**: 20 items per fetch

---

## Dependencies (requirements.txt)
```
fastapi==0.137.2
uvicorn[standard]==0.49.0
pydantic==2.13.4
pandas==3.0.3
numpy==2.4.4
yfinance==1.4.1
httpx==0.28.1
beautifulsoup4==4.15.0
lxml==6.1.1
python-dotenv==1.2.2
apscheduler==3.11.2
aiofiles==25.1.0
feedparser==6.0.12
```

---

## Run Commands
```bash
cd "Trading setup\backend"
pip install -r requirements.txt
cp .env.example .env  # edit with Kite keys if available
python -m app.main
# Open http://localhost:8000
```

### Or launch with start.bat
Double-click `start.bat` in `Trading setup\` — installs deps and starts the server.

---

## Known Limitations
1. **Universe = official NSE Nifty 200 / Nifty 500 constituents** (from archives.nseindia.com CSVs, refreshed only at deploy time). A few symbols intermittently return no data on Yahoo (e.g., TATAMOTORS.NS intraday 404ed during testing) — skipped gracefully with `data_available`/no-signal
2. **FII/DII flows are best-effort** — NSE/MoneyControl are blocked from this network (timeout/503), so `/api/flows` shows "unavailable" until a source is reachable. Breadth is real (NIFTY-200 universe), not full-market
3. **Sector index % may differ fractionally from niftyindices.com** — Yahoo live snapshots vs NSE official figures at different moments
4. **Partial persistence** — portfolio holdings persist to `backend/data/portfolio.json`; signals/trades/news remain in-memory + localStorage only
5. **No authentication** — single user, no API key management
6. **yfinance rate limits** — mitigated by candidate pre-filtering (≤30–50 symbols scanned), 30s quote cache, 300s scanner cache, 3600s daily cache; no fabricated price fallback remains
7. **Intraday signals rely on 15-min delayed Yahoo data** — every intraday card carries an explicit disclaimer; verify live price before entry and use the strict stop loss
8. **Holidays hardcoded** for 2026 only
9. **No backtesting** — no historical signal tracking
10. **No order execution** — Kite Connect not used (unused dependency)

---

## Free-Only Alternative (No Kite)
Replace `market_data.py` with pure yfinance:
- `history(period="1d", interval="5m")` for intraday (15-min delayed)
- `fast_info.last_price` for quotes (15-min delayed)
- `history(period="3mo", interval="1d")` for daily charts
- NSE public CSV for FII/DII (manual or scheduled download)
- NSE option chain HTML scrape for PCR/IV

---

## Extension Points
1. **Add PostgreSQL** → SQLAlchemy models for Signal, Trade, User, NewsCache
2. **Add WebSocket** → push real-time signals (replace polling)
3. **Add Backtester** → pandas + historical data → strategy validation
4. **Add Kite Connect** → live quotes, historical, order placement
5. **Add ML Ranking** → XGBoost on features (RSI, MACD, vol, pattern) → signal score
6. **Add Options** → PCR, max pain, IV percentile for F&O hedging