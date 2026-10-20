import feedparser
from datetime import datetime
from app.models.schemas import NewsItem
import re
import asyncio
from functools import partial

RSS_FEEDS = [
    ("https://news.google.com/rss/search?q=Indian+stock+market+NSE+BSE&hl=en-IN&gl=IN&ceid=IN:en", "Markets"),
    ("https://news.google.com/rss/search?q=FII+DII+flow+Indian+equity&hl=en-IN&gl=IN&ceid=IN:en", "FII/DII"),
    ("https://news.google.com/rss/search?q=Nifty+Sensex+trading+today&hl=en-IN&gl=IN&ceid=IN:en", "Index"),
    ("https://news.google.com/rss/search?q=earnings+results+Indian+stocks&hl=en-IN&gl=IN&ceid=IN:en", "Earnings"),
    ("https://news.google.com/rss/search?q=RBI+policy+interest+rate+India&hl=en-IN&gl=IN&ceid=IN:en", "RBI"),
]

SECTOR_KEYWORDS = {
    "banking": ["bank", "HDFC", "ICICI", "SBI", "Kotak", "Axis", "NPA", "credit"],
    "IT": ["TCS", "Infosys", "Wipro", "HCL", "Tech Mahindra", "IT sector", "digital"],
    "defence": ["HAL", "BEL", "defence", "military", "armed forces"],
    "auto": ["Maruti", "Tata Motors", "M&M", "Bajaj Auto", "Hero", "auto sales", "EV"],
    "pharma": ["Sun Pharma", "Dr Reddy", "Cipla", "pharma", "USFDA"],
    "oil & gas": ["Reliance", "ONGC", "crude", "oil", "BPCL", "IOC", "petroleum"],
    "real estate": ["DLF", "realty", "housing", "real estate", "property"],
    "metals": ["Tata Steel", "JSW", "Hindalco", "metal", "aluminium", "copper"],
    "FMCG": ["HUL", "Nestle", "Britannia", "ITC", "consumer"],
    "NBFC": ["Bajaj Finance", "Shriram", "Muthoot", "NBFC", "microfinance"],
    "insurance": ["LIC", "SBI Life", "HDFC Life", "insurance"],
}

STOCK_PATTERNS = {
    "RELIANCE": [r"(?i)\bReliance\b"],
    "TCS": [r"(?i)\bTCS\b", r"(?i)Tata Consultancy"],
    "HDFCBANK": [r"(?i)\bHDFC Bank\b", r"(?i)\bHDFCBANK\b"],
    "INFY": [r"(?i)\bInfosys\b", r"(?i)\bINFY\b"],
    "ICICIBANK": [r"(?i)\bICICI Bank\b", r"(?i)\bICICIBANK\b"],
    "SBIN": [r"(?i)\bSBI\b", r"(?i)State Bank"],
    "HAL": [r"(?i)\bHAL\b", r"(?i)Hindustan Aeronautics"],
    "BEL": [r"(?i)\bBEL\b", r"(?i)Bharat Electronics"],
    "TRENT": [r"(?i)\bTrent\b"],
    "TITAN": [r"(?i)\bTitan\b"],
    "TATASTEEL": [r"(?i)\bTata Steel\b"],
    "BAJFINANCE": [r"(?i)\bBajaj Finance\b"],
    "MARUTI": [r"(?i)\bMaruti\b"],
    "NTPC": [r"(?i)\bNTPC\b"],
    "POWERGRID": [r"(?i)\bPower Grid\b", r"(?i)\bPOWERGRID\b"],
    "LT": [r"(?i)\bLarsen\b"],
    "SUNPHARMA": [r"(?i)\bSun Pharma\b"],
    "ONGC": [r"(?i)\bONGC\b"],
    "IOC": [r"(?i)\bIOC\b", r"(?i)Indian Oil"],
    "BPCL": [r"(?i)\bBPCL\b"],
    "HPCL": [r"(?i)\bHPCL\b"],
    "DLF": [r"(?i)\bDLF\b"],
    "ZOMATO": [r"(?i)\bZomato\b"],
    "PAYTM": [r"(?i)\bPaytm\b"],
    "IRFC": [r"(?i)\bIRFC\b"],
    "RVNL": [r"(?i)\bRVNL\b"],
}

EVENT_PATTERNS = [
    {"keywords": [r"fraud", r"scam", r"bad loan", r"diversion", r"embezzle", r"forensic"], "type": "fraud", "sector_focus": "banking"},
    {"keywords": [r"rate cut", r"repo rate.*cut", r"lower.*rate", r"easing.*cycle", r"dovish"], "type": "rate_cut"},
    {"keywords": [r"rate hike", r"repo rate.*hike", r"higher.*rate", r"tightening", r"hawkish"], "type": "rate_hike"},
    {"keywords": [r"rate.*unchanged", r"status quo", r"hold.*rate", r"pause"], "type": "rate_hold"},
    {"keywords": [r"fii.*sell", r"foreign.*sell", r"fii.*outflow", r"fii.*pull"], "type": "fii_selling"},
    {"keywords": [r"fii.*buy", r"foreign.*buy", r"fii.*inflow", r"fii.*turn.*buy"], "type": "fii_buying"},
    {"keywords": [r"earnings.*beat", r"profit.*surge", r"revenue.*jump", r"results.*strong", r"beat.*estimate"], "type": "earnings_beat"},
    {"keywords": [r"earnings.*miss", r"profit.*fall", r"loss.*widen", r"results.*weak", r"miss.*estimate", r"disappoint"], "type": "earnings_miss"},
    {"keywords": [r"crash", r"plunge", r"tumble", r"sharp.*fall", r"sell.*off", r"bloodbath"], "type": "crash"},
    {"keywords": [r"rally", r"surge", r"record.*high", r"all.time.*high", r"bull.*run"], "type": "rally"},
    {"keywords": [r"crude.*fall", r"oil.*drop", r"brent.*fall", r"crude.*down", r"opec.*supply"], "type": "oil_fall"},
    {"keywords": [r"crude.*rise", r"oil.*surge", r"brent.*rise", r"crude.*up"], "type": "oil_rise"},
    {"keywords": [r"ipo.*today", r"ipo.*listing", r"ipo.*subscri", r"ipo.*open", r"new.*issue"], "type": "ipo"},
    {"keywords": [r"federal.*reserve", r"us.*rate", r"fed.*policy", r"us.*recession", r"global.*cues"], "type": "global_cues"},
    {"keywords": [r"sebi.*propos", r"sebi.*norm", r"regulat.*tighten", r"f&o.*ban", r"margin.*increas"], "type": "regulation"},
    {"keywords": [r"auto.*sale", r"vehicle.*sale", r"pv.*sale", r"cv.*sale"], "type": "auto_sales"},
    {"keywords": [r"defence.*order", r"military.*order", r"defence.*procure", r"defence.*approv"], "type": "defence_order"},
    {"keywords": [r"rupee.*fall", r"rupee.*weak", r"currency.*deprec", r"dollar.*strong"], "type": "rupee_weak"},
    {"keywords": [r"rupee.*rise", r"rupee.*strengthen", r"currency.*appreci"], "type": "rupee_strong"},
    {"keywords": [r"gold.*rise", r"gold.*surge", r"gold.*high", r"safe.haven", r"geopolitical"], "type": "gold_rise"},
    {"keywords": [r"mid.*cap.*correc", r"small.*cap.*correc", r"broader.*market.*fall"], "type": "midcap_correction"},
    {"keywords": [r"budget.*alloc", r"railway.*budget", r"infra.*spend", r"capex"], "type": "govt_spend"},
]


def _detect_sentiment(title: str, summary: str = "") -> str:
    text = (title + " " + summary).lower()
    pos = ["rally", "surge", "gain", "rise", "high", "bull", "buy", "outperform", "boom", "record", "strong", "beat", "jump", "soar"]
    neg = ["fall", "drop", "crash", "decline", "bear", "sell", "low", "correction", "weak", "loss", "risk", "plunge", "tumble", "miss"]
    p = sum(1 for w in pos if w in text)
    n = sum(1 for w in neg if w in text)
    if p > n:
        return "positive"
    elif n > p:
        return "negative"
    return "neutral"


def _detect_sector(title: str) -> str | None:
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, title, re.IGNORECASE):
                return sector
    return None


def _detect_stocks(title: str) -> list[str]:
    found = []
    for ticker, patterns in STOCK_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, title):
                found.append(ticker)
                break
    return found[:5]


def _detect_events(title: str, summary: str = "") -> list[dict]:
    text = title + " " + summary
    matched = []
    for ep in EVENT_PATTERNS:
        for kw in ep["keywords"]:
            if re.search(kw, text, re.IGNORECASE):
                matched.append(ep)
                break
    return matched


def _generate_impact(title: str, summary: str, sentiment: str, sector: str | None, stocks: list[str], events: list[dict]) -> dict:
    text = (title + " " + summary).lower()
    event_types = [e["type"] for e in events]
    stock_list = ", ".join(stocks) if stocks else "related sector stocks"

    if "fraud" in event_types:
        return {
            "prediction": f"Affected bank stock(s) likely to face selling pressure for 2-3 sessions. Sector-wide sentiment hit if the fraud is large. Watch for regulatory action and contagion to banks with weak asset quality.",
            "caution": f"Avoid {stock_list} until clarity emerges. Don't average down on the affected bank. Check if your MF or portfolio has indirect exposure through the bank's lending book or bond holdings.",
            "dos": [
                f"Exit or reduce {stock_list} if directly affected",
                "Check portfolio for indirect exposure via NBFC/MF holdings",
                "Wait for forensic audit details before re-entering",
                "Look for quality banks (HDFCBANK, ICICIBANK) on oversold dips later"
            ],
            "donts": [
                "Don't catch the falling knife on the affected bank",
                "Don't assume all banks are equally impacted — wait for data",
                "Don't ignore SEBI/RBI statements on the matter",
                "Don't panic-sell all banking stocks — contagion is usually limited"
            ],
        }

    if "rate_cut" in event_types:
        return {
            "prediction": "Rate-sensitive sectors (banks, auto, real estate) likely to rally. Banking NIMs may compress but credit growth accelerates. Real estate and auto benefit from lower EMIs.",
            "caution": "Rate-cut rallies can be front-run and reversed. Don't chase after a 3-5% single-day pop. Actual transmission to borrowers takes 2-3 quarters.",
            "dos": [
                "Accumulate quality banks (HDFCBANK, ICICIBANK) on dips",
                "Add auto stocks (MARUTI, M&M) — lower EMIs boost demand",
                "Consider real estate (DLF) for medium-term gains",
                "Increase allocation to bond funds / duration funds"
            ],
            "donts": [
                "Don't chase after rate-cut news is already priced in",
                "Don't ignore bank NIM compression risk",
                "Don't go all-in on rate-sensitives in one trade",
                "Don't forget global rate environment — US Fed matters too"
            ],
        }

    if "rate_hike" in event_types:
        return {
            "prediction": "Rate-sensitive sectors (banks, auto, real estate) face headwinds. FII outflows likely as bond yields rise. High-debt companies hurt by higher interest costs.",
            "caution": "Reduce exposure to rate-sensitives. Defensive sectors (IT, pharma, FMCG) relatively safer. Watch if RBI signals further hikes ahead.",
            "dos": [
                "Shift towards defensive sectors — IT, pharma, FMCG",
                "Reduce leverage — avoid margin trading",
                "Look at companies with low debt and strong cash flows",
                "Consider gold as an inflation hedge"
            ],
            "donts": [
                "Don't hold highly leveraged companies through a hiking cycle",
                "Don't ignore the impact on real estate demand",
                "Don't assume RBI will stop at one hike — watch forward guidance",
                "Don't panic-sell quality banks — NIM improvement benefits them"
            ],
        }

    if "rate_hold" in event_types:
        return {
            "prediction": "Rate pause signals RBI is watching inflation data. Markets see mild relief as no tightening surprise. Rate-sensitives stay in a holding pattern.",
            "caution": "A pause is not a signal to go all-in. Watch RBI's commentary for future direction. If inflation stays elevated, a hike could follow.",
            "dos": [
                "Maintain current allocation to banking and rate-sensitives",
                "Watch RBI's inflation outlook commentary closely",
                "Use this stability to rebalance your portfolio",
                "Accumulate quality stocks gradually"
            ],
            "donts": [
                "Don't assume a pause means a cut is next",
                "Don't make large bets based on the pause alone",
                "Don't ignore inflation data releases in coming weeks",
                "Don't overtrade on the announcement day"
            ],
        }

    if "fii_selling" in event_types:
        return {
            "prediction": "FII selling puts pressure on large-caps (RELIANCE, HDFCBANK, INFY, TCS) which they typically own. Mid/small-caps may see indirect pressure through MF redemptions. Rupee may weaken further.",
            "caution": "FII selling can persist for weeks. Don't assume it's a one-day event. Watch DII data — if DIIs absorb the selling, it's a positive signal for recovery.",
            "dos": [
                "Reduce position sizes in FII-heavy large-caps",
                "Increase cash allocation to 20-30% of portfolio",
                "Watch DII buying data — their support limits downside",
                "Look for defensive sectors (IT, pharma) for shelter"
            ],
            "donts": [
                "Don't assume FII selling will stop tomorrow",
                "Don't aggressively buy the dip on large-caps",
                "Don't ignore rupee depreciation impact on portfolios",
                "Don't sell quality small-caps in panic — they recover fastest"
            ],
        }

    if "fii_buying" in event_types:
        return {
            "prediction": "FII inflows support large-cap valuations and improve market breadth. Sectors they typically buy (banking, IT, consumer) likely to lead. Rupee stabilizes with dollar inflows.",
            "caution": "FII flows can reverse quickly if global risk sentiment changes. Don't assume sustained buying — watch if DII selling offsets FII buying.",
            "dos": [
                "Increase allocation to FII-favored sectors (banking, IT, consumption)",
                "Hold quality large-caps with strong earnings visibility",
                "Consider increasing equity allocation gradually",
                "Track FII derivative positioning for trend confirmation"
            ],
            "donts": [
                "Don't assume FII buying will last forever",
                "Don't ignore DII selling patterns — they often sell into FII buying",
                "Don't go all-in at once — scale into positions",
                "Don't forget global risk events can reverse flows overnight"
            ],
        }

    if "earnings_beat" in event_types:
        stock_mention = f"{stock_list}" if stocks else "the reporting company"
        return {
            "prediction": f"{stock_mention} likely to gap up on strong results. Short-term momentum positive. Watch if management guidance supports the beat or if it's a one-time item.",
            "caution": "Post-earnings gaps can reverse in 1-2 sessions if broader market is weak. Don't chase after a 5%+ gap up — wait for a pullback to entry zone.",
            "dos": [
                f"Hold {stock_list} if you already own — strong results support the thesis",
                "Wait for a pullback if you want to enter — don't chase gap-ups",
                "Check management commentary for forward guidance",
                "Compare with peer results to confirm sector-wide strength"
            ],
            "donts": [
                "Don't chase a stock after 5%+ gap up on earnings",
                "Don't ignore if the beat is on one-time items vs operational improvement",
                "Don't hold through next quarter without checking guidance",
                "Don't compare with peers without checking their timelines"
            ],
        }

    if "earnings_miss" in event_types:
        stock_mention = f"{stock_list}" if stocks else "the reporting company"
        return {
            "prediction": f"{stock_mention} likely to face selling pressure. If the miss is operational (not one-time), recovery may take 1-2 quarters. Watch for management guidance and peer comparisons.",
            "caution": "Don't panic-sell on earnings miss alone — check if the miss is structural or one-time. If fundamentals are intact, use the dip to accumulate.",
            "dos": [
                f"Review if {stock_list} miss is structural or one-time",
                "Wait for 2-3 sessions before re-entering — let dust settle",
                "Check if sector peers also reported weak numbers",
                "If long-term thesis intact, use the dip to add slowly"
            ],
            "donts": [
                "Don't panic-sell on earnings miss alone",
                "Don't average down aggressively without understanding the miss",
                "Don't ignore management commentary — guidance matters more than results",
                "Don't assume the stock will recover immediately"
            ],
        }

    if "crash" in event_types:
        return {
            "prediction": "Sharp market sell-offs often overshoot in the short term. A technical bounce is likely within 2-3 sessions. Watch for stabilization in global markets and DII buying as recovery signals.",
            "caution": "Avoid catching falling knives. Wait for at least 2 green candles before adding. Panic selling locks in permanent losses. Quality stocks recover fastest.",
            "dos": [
                "Maintain stop losses — don't remove them in panic",
                "Keep 20-30% cash for deployment on recovery",
                "Watch DII buying — their support signals a floor",
                "Prepare a wish list of quality stocks to buy on recovery"
            ],
            "donts": [
                "Don't panic-sell quality stocks at the bottom",
                "Don't aggressively average all losing positions",
                "Don't use margin/leverage during high-volatility crashes",
                "Don't ignore stop losses hoping for a bounce"
            ],
        }

    if "rally" in event_types:
        return {
            "prediction": "Strong rallies often extend 1-2 more sessions as FOMO kicks in. However, overbought conditions build quickly. Watch for divergence between Nifty and breadth — if breadth narrows, rally is losing steam.",
            "caution": "Don't mistake a rally for a permanent trend. Book partial profits on strong moves. A 3-5% correction after a strong rally is normal and healthy.",
            "dos": [
                "Book partial profits (20-30%) on strong rallies",
                "Trail stop losses to protect gains",
                "Watch market breadth — narrowing breadth = weaker rally",
                "Hold quality positions with trailing stops"
            ],
            "donts": [
                "Don't go all-in chasing a rally that's already extended",
                "Don't ignore overbought RSI signals (>75 on daily)",
                "Don't remove stop losses because 'market is going up'",
                "Don't forget that pullbacks after rallies are normal"
            ],
        }

    if "oil_fall" in event_types:
        return {
            "prediction": "Lower crude benefits OMCs (IOC, BPCL, HPCL) with higher marketing margins. Aviation stocks (IndiGo) gain on lower fuel costs. RIL's refining margins may compress slightly.",
            "caution": "If supply increase doesn't materialize, crude can bounce back sharply. Book partial profits in OMCs — they're volatile. Don't assume crude stays low forever.",
            "dos": [
                "Buy OMCs (IOC, BPCL, HPCL) on dips for marketing margin benefit",
                "Reduce upstream exposure (ONGC) if crude was their earnings driver",
                "Monitor OPEC+ meeting outcomes for supply direction",
                "Consider aviation stocks for fuel cost benefit"
            ],
            "donts": [
                "Don't assume crude will stay low — geopolitics can reverse it overnight",
                "Don't chase OMCs after a big gap up on oil fall",
                "Don't ignore upstream company earnings impact (ONGC)",
                "Don't go heavy on oil-sensitive trades without stop losses"
            ],
        }

    if "oil_rise" in event_types:
        return {
            "prediction": "Higher crude hurts OMCs (IOC, BPCL, HPCL) as they absorb price hikes. Upstream companies (ONGC) benefit. Current account deficit widens putting pressure on rupee. Inflation concerns rise.",
            "caution": "OMC stocks will face selling pressure. Don't try to catch the bottom. Upstream gains may be offset by government windfall tax risk. Watch RBI's inflation commentary.",
            "dos": [
                "Reduce OMC exposure (IOC, BPCL, HPCL) until crude stabilizes",
                "Consider upstream (ONGC) for crude-linked earnings benefit",
                "Watch rupee — crude rise weakens INR which hurts IT imports",
                "Increase allocation to defensive sectors (IT, pharma, FMCG)"
            ],
            "donts": [
                "Don't hold OMCs without stop losses during crude surge",
                "Don't assume upstream gains are permanent — windfall tax risk exists",
                "Don't ignore inflation impact on RBI rate decisions",
                "Don't panic-sell everything — energy is just one sector"
            ],
        }

    if "ipo" in event_types:
        return {
            "prediction": "IPO listings can be volatile in the first 2-3 sessions. GMP (grey market premium) indicates listing expectation but doesn't guarantee post-listing performance.",
            "caution": "Don't apply to every IPO without checking fundamentals. Listing gains are not guaranteed — many IPOs list below issue price in weak markets. Apply only if you understand the business.",
            "dos": [
                "Check the company's financials and valuation vs peers before applying",
                "Track GMP but don't rely on it — it's speculative",
                "Apply for long-term only if fundamentals are strong",
                "Set a stop loss if listing at a premium — don't hold blindly"
            ],
            "donts": [
                "Don't apply to IPOs just because of hype or GMP",
                "Don't invest more than 5% of portfolio in a single IPO",
                "Don't hold through listing loss hoping for recovery — cut if thesis broken",
                "Don't ignore lock-in expiry dates for OFS/FPO shares"
            ],
        }

    if "global_cues" in event_types:
        return {
            "prediction": "Global events (US Fed, geopolitical tensions, US data) impact Indian markets via FII flows and risk sentiment. Strong US data = dollar strength = FII outflows from India. Weak data = opposite.",
            "caution": "Indian markets don't operate in isolation. US market overnight movement sets the tone for Asian and Indian markets. Watch SGX Nifty for early cues.",
            "dos": [
                "Monitor US market futures and SGX Nifty before market open",
                "Keep position sizes smaller ahead of major global events",
                "Diversify across sectors to reduce single-event risk",
                "Use options/hedging if holding large positions before global events"
            ],
            "donts": [
                "Don't ignore overnight US market movements",
                "Don't take large positions ahead of US Fed meetings",
                "Don't assume India is insulated from global sell-offs",
                "Don't trade based on headlines alone — wait for confirmation"
            ],
        }

    if "regulation" in event_types:
        return {
            "prediction": "SEBI/regulatory changes impact specific segments immediately. F&O restrictions reduce retail speculative volumes. Higher margins reduce leverage-driven trading. Broking stocks may see short-term impact.",
            "caution": "Regulatory changes take time to fully impact. Don't overreact on announcement day. Focus on which specific companies/segments are most affected.",
            "dos": [
                "Review your F&O positions if new margin rules apply",
                "Shift focus to cash market if F&O barriers increase",
                "Check if broking stocks in portfolio are impacted",
                "Adapt strategy to new rules before they take effect"
            ],
            "donts": [
                "Don't panic-sell broking stocks on regulatory news",
                "Don't assume you can ignore new rules — they will be enforced",
                "Don't take aggressive F&O positions ahead of regulatory deadlines",
                "Don't assume the impact is only on others — check your own positions"
            ],
        }

    if "auto_sales" in event_types:
        return {
            "prediction": "Monthly auto sales data is a demand indicator. Strong PV/CV sales signal economic recovery. Two-wheeler sales reflect rural demand. EV adoption is a structural tailwind for some companies.",
            "caution": "Auto sales are cyclical and seasonal. Don't extrapolate one strong month as a permanent trend. Watch inventory levels at dealerships for forward demand signals.",
            "dos": [
                "Buy segment leaders (MARUTI for PV, M&M for UV/tractor, TATAMOTORS for CV/EV)",
                "Check dealer inventory levels — high inventory means demand may slow",
                "Focus on EV transition stories (TATAMOTORS, M&M) for long-term",
                "Compare YoY sales, not just MoM, to filter seasonality"
            ],
            "donts": [
                "Don't extrapolate one month's sales as a trend",
                "Don't ignore channel checks — dealer inventory matters",
                "Don't buy weak auto companies just because sector is doing well",
                "Don't ignore input cost pressures on auto margins"
            ],
        }

    if "defence_order" in event_types:
        return {
            "prediction": "Defence orders provide multi-year revenue visibility. HAL and BEL are primary beneficiaries. Order book growth supports premium valuations. Export orders are an incremental catalyst.",
            "caution": "Defence stocks have run up significantly on order wins. Execution risk remains — delayed deliveries can impact revenue recognition. Valuations are stretched at current levels.",
            "dos": [
                "Accumulate HAL and BEL on 10-15% corrections — they are best positioned",
                "Check order book-to-revenue ratio for execution visibility",
                "Consider defence ETF for diversification across the sector",
                "Hold for 3-5 year horizon — defence spending is structural"
            ],
            "donts": [
                "Don't chase after 10%+ single-day rallies on order news",
                "Don't ignore valuation risks — many defence stocks trade at 50x+ PE",
                "Don't over-allocate beyond 10-15% to one sector",
                "Don't forget execution risk — orders don't equal revenue immediately"
            ],
        }

    if "rupee_weak" in event_types:
        return {
            "prediction": "Weak rupee benefits export-heavy sectors (IT, pharma) through forex gains. Import-heavy sectors (oil, metals, chemicals) face margin pressure. FII outflows accelerate as dollar-denominated returns fall.",
            "caution": "Sustained rupee weakness is inflationary — RBI may intervene. Don't assume weakness is permanent. Watch RBI's forex reserve data and intervention signals.",
            "dos": [
                "Increase allocation to IT (TCS, INFY, WIPRO) for rupee depreciation benefit",
                "Consider pharma exports (SUNPHARMA, DRREDDY) for forex tailwind",
                "Reduce exposure to import-heavy sectors (oil, metals)",
                "Watch RBI intervention signals — they set a floor on depreciation"
            ],
            "donts": [
                "Don't assume rupee will keep weakening forever",
                "Don't ignore RBI's capacity to intervene (forex reserves)",
                "Don't chase IT stocks purely on rupee — check their organic growth",
                "Don't ignore the inflationary impact on your portfolio"
            ],
        }

    if "rupee_strong" in event_types:
        return {
            "prediction": "Strong rupee hurts IT/pharma export margins. Import-heavy sectors benefit from cheaper imports. FII inflows likely supporting the rupee — positive for overall market sentiment.",
            "caution": "IT sector may see 1-2% margin compression for every 1% rupee appreciation. Don't panic-sell IT — fundamentals matter more than FX in the long run.",
            "dos": [
                "Consider reducing IT/pharma if rupee strength is sustained",
                "Increase allocation to domestic-focused sectors (banks, consumption)",
                "Beneficiaries: import-heavy sectors (oil marketing, chemicals)",
                "Focus on IT companies with strong pricing power (TCS, INFY)"
            ],
            "donts": [
                "Don't panic-sell IT stocks on rupee strength alone",
                "Don't ignore that strong rupee can reverse quickly",
                "Don't assume import-heavy sectors will permanently benefit",
                "Don't forget global factors drive FII flows and rupee"
            ],
        }

    if "gold_rise" in event_types:
        return {
            "prediction": "Gold acts as a safe-haven during geopolitical uncertainty. If tensions persist, gold may test higher levels. Jewellery stocks (TITAN) face higher input costs but benefit from consumer demand.",
            "caution": "Gold rallies on geopolitical fears can reverse quickly if tensions de-escalate. Don't over-allocate at peak euphoria. 10-15% gold allocation is optimal.",
            "dos": [
                "Maintain 10-15% portfolio allocation to gold as hedge",
                "Buy on dips to ₹68,000-70,000 range if available",
                "Consider Sovereign Gold Bonds for tax-efficient gold exposure",
                "Watch TITAN for jewellery demand impact — input cost pressure"
            ],
            "donts": [
                "Don't over-allocate to gold at all-time highs",
                "Don't use leverage for gold buying",
                "Don't ignore that gold doesn't generate income — it's a hedge only",
                "Don't assume geopolitical tensions will persist indefinitely"
            ],
        }

    if "midcap_correction" in event_types:
        return {
            "prediction": "Mid/small-cap corrections are healthy when valuations are stretched. Quality companies with strong earnings growth recover fastest. Broad market correction often creates long-term buying opportunities.",
            "caution": "Don't try to time the exact bottom. Some mid-caps may correct further 10-15% from current levels. Focus on fundamentals — companies with >20% earnings growth recover first.",
            "dos": [
                "Start SIPs in quality mid-cap mutual funds for systematic entry",
                "Buy industry leaders with strong fundamentals on further dips",
                "Maintain adequate cash — deploy gradually, not all at once",
                "Focus on companies with 20%+ earnings growth and reasonable PE"
            ],
            "donts": [
                "Don't try to time the exact bottom — it's impossible",
                "Don't buy stocks just because they corrected 20% from peak",
                "Don't ignore FII flow data — their selling drives mid-cap weakness",
                "Don't use leverage to buy mid-caps during corrections"
            ],
        }

    if "govt_spend" in event_types:
        return {
            "prediction": "Government capex spending benefits infrastructure, railway, and defence companies. Order book visibility improves for companies like L&T, IRCON, RVNL. Budget allocation is a key catalyst.",
            "caution": "Budget-related rallies are often buy-the-rumor, sell-the-fact events. Don't chase stocks purely on budget expectations. Execution of government spending matters more than announcements.",
            "dos": [
                "Accumulate infra plays (L&T, IRCON, RVNL) before budget if thesis is strong",
                "Focus on companies with proven execution track records",
                "Check order book visibility — past execution predicts future deliveries",
                "Consider railway PSUs (IRFC, RVNL) for structural capex story"
            ],
            "donts": [
                "Don't chase budget-related stocks after 10%+ rally",
                "Don't buy weak companies just because they operate in a favored sector",
                "Don't forget that government spending announcements don't equal actual revenue",
                "Don't ignore valuation concerns in railway/infra PSUs"
            ],
        }

    # ── SECTOR-SPECIFIC FALLBACKS ──
    if sector == "banking":
        return {
            "prediction": f"Banking sector in focus. Watch asset quality trends and credit growth data. {stock_list if stocks else 'Major banks (HDFCBANK, ICICIBANK, SBIN)'} to lead any sector move.",
            "caution": "Banking stocks are sensitive to macro data (inflation, rate decisions, NPA trends). Don't take large positions ahead of RBI policy or quarterly results.",
            "dos": [
                "Focus on banks with strong asset quality (low NPA, high provision coverage)",
                "Track credit growth and NIM trends quarterly",
                "Use Nifty Bank ETF for diversified sector exposure",
                "Accumulate quality banks on corrections"
            ],
            "donts": [
                "Don't ignore NPA data — it's the key risk metric for banks",
                "Don't hold weak PSU banks with high NPAs for dividend yield alone",
                "Don't over-allocate to banking beyond 25-30% of portfolio",
                "Don't trade banking stocks without stop losses during volatility"
            ],
        }

    if sector == "IT":
        return {
            "prediction": f"IT sector in focus. Watch deal wins, US client spending, and attrition data. {stock_list if stocks else 'TCS, INFY, WIPRO, HCLTECH'} are key bellwethers.",
            "caution": "IT sector is cyclical and sensitive to global demand. Don't assume past growth rates will continue. Watch for margin pressure from wage hikes and visa costs.",
            "dos": [
                "Focus on companies with strong deal wins and margin expansion",
                "Accumulate large-cap IT (TCS, INFY) on dips for long-term",
                "Consider IT ETFs for diversified exposure",
                "Track attrition rates as a leading indicator of demand"
            ],
            "donts": [
                "Don't chase mid-cap IT without understanding their client concentration",
                "Don't ignore margin pressure from wage inflation",
                "Don't assume pre-2022 growth rates will return",
                "Don't ignore US recession risk — it directly impacts IT spending"
            ],
        }

    if sector == "defence":
        return {
            "prediction": f"Defence sector in focus. Multi-year order visibility supports valuations. {stock_list if stocks else 'HAL, BEL'} are primary beneficiaries of government spending.",
            "caution": "Defence stocks are at premium valuations after a strong run. Execution risk exists — delayed deliveries impact revenue. Don't chase after big single-day rallies.",
            "dos": [
                "Accumulate HAL and BEL on 10-15% corrections",
                "Consider defence ETF for sector diversification",
                "Hold for 3-5 year horizon — defence spending is structural",
                "Track order book-to-revenue ratio for execution visibility"
            ],
            "donts": [
                "Don't chase after 10%+ single-day rally on order news",
                "Don't ignore valuation risks — many at 50x+ PE",
                "Don't over-allocate to one defence stock",
                "Don't forget execution risk — orders take time to convert to revenue"
            ],
        }

    if sector == "auto":
        return {
            "prediction": f"Auto sector in focus. Watch monthly sales data, EV adoption, and input costs. {stock_list if stocks else 'Segment leaders (MARUTI, M&M, TATAMOTORS)'} to lead the sector.",
            "caution": "Auto sales are cyclical and seasonal. Don't extrapolate one month's data. Watch dealer inventory and commodity prices for margin impact.",
            "dos": [
                "Buy segment leaders — MARUTI (PV), M&M (UV/tractor), TATAMOTORS (CV/EV)",
                "Check dealer inventory levels before investing",
                "Focus on EV transition stories for long-term structural growth",
                "Compare YoY sales to filter out seasonality"
            ],
            "donts": [
                "Don't extrapolate one month's sales as a permanent trend",
                "Don't ignore input cost pressures on auto margins",
                "Don't buy weak auto companies just because sector is doing well",
                "Don't ignore EV disruption risk for traditional players"
            ],
        }

    # ── GENERIC FALLBACK (should rarely hit now) ──
    if sentiment == "positive":
        return {
            "prediction": f"{stock_list} likely to see continued buying interest. Watch for follow-through volume to confirm the trend. Broader market sentiment supports the move.",
            "caution": "Profit booking possible after a strong move. Don't chase after a large gap up. Use trailing stops to protect gains.",
            "dos": [
                "Book partial profits on sharp rallies (20-30%)",
                "Trail stop losses to protect unrealized gains",
                "Watch for volume confirmation of the trend",
                "Hold quality positions with disciplined stops"
            ],
            "donts": [
                "Don't chase after a big gap up — wait for pullback",
                "Don't remove stop losses because the stock is going up",
                "Don't over-leverage on the rally",
                "Don't ignore global cues that could reverse sentiment"
            ],
        }

    if sentiment == "negative":
        return {
            "prediction": f"{stock_list} may face selling pressure. Support levels need to hold for recovery. Watch for stabilization signals before adding positions.",
            "caution": "Avoid catching falling knives. Wait for at least 2 green sessions before adding. Quality stocks recover fastest from corrections.",
            "dos": [
                "Reduce position sizes in the affected names",
                "Hold stop losses tight — don't remove them",
                "Maintain cash reserves for deployment on recovery",
                "Watch for DII buying as a support signal"
            ],
            "donts": [
                "Don't panic-sell quality stocks at the bottom",
                "Don't aggressively average all losing positions",
                "Don't ignore stop losses hoping for a bounce",
                "Don't assume the correction will be over in one session"
            ],
        }

    return {
        "prediction": f"Market watching {sector or 'broader indices'} for direction. {stock_list} in focus. Watch for volume and breadth confirmation of any move.",
        "caution": "Stay nimble in uncertain conditions. Use well-defined stop losses and position sizes. Don't take large directional bets without confirmation.",
        "dos": [
            "Trade within well-defined ranges with clear stop losses",
            "Focus on stock-specific action rather than broad bets",
            "Maintain disciplined position sizing (2-3% risk per trade)",
            "Watch for volume confirmation before entering"
        ],
        "donts": [
            "Don't take large directional bets without confirmation",
            "Don't ignore stop losses in uncertain markets",
            "Don't overtrade — quality setups over quantity",
            "Don't ignore risk management for any single position"
        ],
    }


class NewsAggregator:
    async def _parse_feed(self, url: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(feedparser.parse, url))

    async def fetch_all(self) -> list[NewsItem]:
        items: list[NewsItem] = []
        seen_titles: set[str] = set()

        for url, default_sector in RSS_FEEDS:
            try:
                feed = await self._parse_feed(url)
                for entry in feed.entries[:12]:
                    title = entry.get("title", "").strip()
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)

                    published = entry.get("published", "")
                    if published:
                        try:
                            dt = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z")
                            pub_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            try:
                                dt = datetime.strptime(published[:25], "%a, %d %b %Y %H:%M:%S")
                                pub_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                pub_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        pub_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    link = entry.get("link", "")
                    summary = entry.get("summary", "")
                    clean_summary = re.sub(r"<[^>]+>", "", summary)[:200] if summary else ""
                    sentiment = _detect_sentiment(title, clean_summary)
                    sector = _detect_sector(title) or default_sector
                    stocks = _detect_stocks(title)
                    events = _detect_events(title, clean_summary)
                    impact = _generate_impact(title, clean_summary, sentiment, sector, stocks, events)

                    source_name = "Google News"
                    if hasattr(entry.get("source"), "get"):
                        source_name = entry["source"].get("title", source_name)

                    items.append(NewsItem(
                        id=f"news_{len(items)}",
                        title=title,
                        source=source_name,
                        url=link,
                        published_at=pub_str,
                        summary=clean_summary if clean_summary else None,
                        sentiment=sentiment,
                        affected_stocks=stocks if stocks else None,
                        sector=sector,
                        prediction=impact["prediction"],
                        caution=impact["caution"],
                        dos=impact["dos"],
                        donts=impact["donts"],
                    ))
            except Exception as e:
                print(f"[News] RSS error ({default_sector}): {e}")
                continue

        items.sort(key=lambda x: x.published_at, reverse=True)
        return items


news_aggregator = NewsAggregator()
