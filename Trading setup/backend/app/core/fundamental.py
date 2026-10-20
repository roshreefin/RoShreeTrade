import re
import threading
import time

import requests
from bs4 import BeautifulSoup

CACHE_TTL_SECONDS = 6 * 3600
SCREENER_BASE = "https://www.screener.in/company/{}/"
REQUEST_TIMEOUT = 30

SYMBOL_ALIASES = {
    "M&M": "MM",
    "BAJAJ-AUTO": "BAJAJ-AUTO",
    "M&MFIN": "M&MFIN",
    "GODREJPROP": "GODREJPROP",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _to_float(txt: str) -> float | None:
    if not txt:
        return None
    txt = txt.replace(",", "").replace("\xa0", " ")
    m = re.search(r"-?\d+(?:\.\d+)?", txt)
    if not m:
        return None
    try:
        return float(m.group(0))
    except (TypeError, ValueError):
        return None


def _clean_label(txt: str) -> str:
    txt = (txt or "").strip()
    txt = re.sub(r"\s+\+\s*$", "", txt).strip()
    return txt


def _series_map(cells, value_getter) -> dict[str, float | None]:
    out = {}
    for cell in cells:
        key = cell.get("data-date-key") or cell.get_text(" ", strip=True) or "col"
        if not key or key == "col":
            key = cell.get_text(" ", strip=True)
        out[key] = _to_float(value_getter(cell))
    return out


class FundamentalAnalyzer:
    def __init__(self):
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def _cached(self, symbol: str) -> dict | None:
        entry = self._cache.get(symbol)
        if entry and time.time() - entry[0] < CACHE_TTL_SECONDS:
            return entry[1]
        return None

    def _store(self, symbol: str, data: dict) -> None:
        with self._lock:
            self._cache[symbol] = (time.time(), data)

    def _fetch(self, symbol: str) -> BeautifulSoup | None:
        url = SCREENER_BASE.format(symbol)
        for attempt in range(3):
            try:
                resp = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
                                    timeout=REQUEST_TIMEOUT)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 200:
                    return BeautifulSoup(resp.text, "lxml")
            except Exception:
                pass
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
        return None

    def _parse_data_table(self, section) -> dict | None:
        table = section.find("table", class_="data-table")
        if not table:
            return None
        thead = table.find("thead")
        tbody = table.find("tbody")
        if not thead or not tbody:
            return None
        header_th = thead.find("tr").find_all("th")
        if not header_th:
            return None
        headers = [th.get_text(" ", strip=True) for th in header_th]
        date_keys = [th.get("data-date-key") or "" for th in header_th]
        rows = {}
        for tr in tbody.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            label = _clean_label(tds[0].get_text(" ", strip=True))
            cells = tds[1:]
            values = {}
            for th, td in zip(header_th[1:], cells):
                key = th.get("data-date-key") or th.get_text(" ", strip=True)
                values[key] = _to_float(td.get_text(" ", strip=True))
            rows[label] = {"headers": headers[1:], "date_keys": date_keys[1:], "values": values}
        return {"headers": headers, "date_keys": date_keys, "rows": rows}

    def _parse_top_ratios(self, soup) -> dict:
        out = {}
        ul = soup.select_one("ul#top-ratios")
        if not ul:
            return out
        for li in ul.find_all("li"):
            name_el = li.find("span", class_="name")
            value_el = li.find("span", class_="value")
            if not name_el or not value_el:
                continue
            name = name_el.get_text(" ", strip=True)
            raw = value_el.get_text(" ", strip=True)
            nums = re.findall(r"-?\d+(?:\.\d+)?", raw.replace(",", ""))
            body = value_el.get_text(" ", strip=True)
            out[name] = {"raw": raw, "nums": [_to_float(n) for n in nums], "body": body}
        return out

    def _annual_series(self, table: dict, labels: tuple[str, ...]) -> tuple[list[tuple[int, float]], float | None]:
        if not table:
            return [], None
        row = None
        for label in labels:
            if label in table["rows"]:
                row = table["rows"][label]
                break
        if not row:
            return [], None
        annual = []
        ttm = None
        for idx, key in enumerate(row["date_keys"]):
            if key == "TTM":
                ttm = row["values"].get("TTM")
                continue
            if not key:
                continue
            m = re.search(r"(20\d{2})", key)
            if not m:
                continue
            val = row["values"].get(key)
            if val is None:
                continue
            annual.append((int(m.group(1)), val))
        annual.sort(key=lambda x: x[0])
        return annual, ttm

    def _latest_prev(self, series: list[tuple[int, float]]):
        vals = [v for _, v in series if v is not None]
        if not vals:
            return None, None
        latest = vals[-1]
        prev = vals[-2] if len(vals) >= 2 else None
        return latest, prev

    def _growth(self, series: list[tuple[int, float]]) -> float | None:
        vals = [v for _, v in series if v is not None]
        if len(vals) >= 2 and vals[-2]:
            return (vals[-1] / vals[-2] - 1) * 100
        return None

    def _cagr(self, series: list[tuple[int, float]]) -> float | None:
        if len(series) >= 3 and series[0][1] and series[-1][1]:
            years = series[-1][0] - series[0][0]
            if years > 0:
                return ((series[-1][1] / series[0][1]) ** (1 / years) - 1) * 100
        return None

    _MONTHS = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
               7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

    def _q_label(self, key: str) -> str:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", key or "")
        if m:
            try:
                return f"{self._MONTHS.get(int(m.group(2)), m.group(2))} {m.group(1)}"
            except Exception:
                pass
        return key or ""

    def _quarter_momentum(self, table: dict, sales_labels: tuple[str, ...], profit_label: str) -> list[dict]:
        if not table:
            return []
        row_s = None
        for label in sales_labels:
            if label in table["rows"]:
                row_s = table["rows"][label]
                break
        row_p = table["rows"].get(profit_label)
        if not row_s:
            return []
        keys = [k for k in row_s["date_keys"] if k]
        out = []
        for idx, key in enumerate(keys):
            q = {
                "q": self._q_label(key),
                "sales": row_s["values"].get(key),
                "net_profit": row_p["values"].get(key) if row_p else None,
            }
            out.append(q)
        return [q for q in out if q["sales"] is not None or q["net_profit"] is not None]

    def get_analysis(self, ticker: str) -> dict:
        symbol = SYMBOL_ALIASES.get(ticker.upper(), ticker.upper())
        cached = self._cached(symbol)
        if cached:
            return cached

        soup = self._fetch(symbol)
        if soup is None:
            data = {
                "ticker": ticker.upper(), "name": None, "source": "screener.in",
                "available": False,
                "error": "No page found on screener.in for this ticker.",
                "disclaimer": "Data source: https://www.screener.in — not investment advice.",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._store(symbol, data)
            return data

        top = self._parse_top_ratios(soup)

        sections = {}
        for sid in ("quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios", "shareholding"):
            sec = soup.find("section", id=sid)
            if sec:
                sections[sid] = self._parse_data_table(sec)

        name_el = soup.find("h1")
        name = name_el.get_text(" ", strip=True) if name_el else None

        sector = industry = None
        peers = soup.find("section", id="peers")
        if peers:
            for a in peers.find_all("a"):
                t = (a.get("title") or "").strip()
                txt = a.get_text(" ", strip=True)
                if t == "Sector":
                    sector = txt
                elif t == "Industry":
                    industry = txt

        pl = sections.get("profit-loss")
        bs = sections.get("balance-sheet")
        cf = sections.get("cash-flow")
        ratios = sections.get("ratios")
        share = sections.get("shareholding")
        quarters = sections.get("quarters")

        payroll, pl_ttm = (self._annual_series(pl, ("Sales", "Revenue", "Total Revenue", "Operating Revenue")) if pl else ([], None))
        rev = self._latest_prev(payroll)
        np_row, np_ttm = (self._annual_series(pl, ("Net Profit", "Profit After Tax", "PAT")) if pl else ([], None))
        npv = self._latest_prev(np_row)
        opm_row, opm_ttm = (self._annual_series(pl, ("OPM %", "Operating Margin", "Operating Margin %", "Financing Margin %")) if pl else ([], None))
        opmv = self._latest_prev(opm_row)

        metrics = {
            "revenue": {"latest": rev[0], "prev": rev[1], "ttm": pl_ttm,
                        "cagr": self._cagr(payroll), "growth": self._growth(payroll)},
            "net_profit": {"latest": npv[0], "prev": npv[1], "ttm": np_ttm,
                           "cagr": self._cagr(np_row), "growth": self._growth(np_row)},
            "opm": {"latest": opmv[0], "prev": opmv[1], "ttm": opm_ttm},
        }
        if rev[0]:
            if npv[0] is not None:
                metrics["net_margin"] = round(npv[0] / rev[0] * 100, 2)
            if opmv[0] is not None:
                metrics["opm"] = {"latest": opmv[0], "prev": opmv[1], "ttm": opm_ttm}

        borrow_row, _ = (self._annual_series(bs, ("Borrowings", "Total Debt", "Debt")) if bs else ([], None))
        borrows = self._latest_prev(borrow_row)
        equity_row, _ = (self._annual_series(bs, ("Equity Capital", "Share Capital")) if bs else ([], None))
        reserves_row, _ = (self._annual_series(bs, ("Reserves", "Surplus", "Total Shareholders Funds")) if bs else ([], None))
        eq = self._latest_prev(equity_row)[0]
        res = self._latest_prev(reserves_row)[0]
        borrow_latest = borrows[0]
        equity_total = (eq or 0) + (res or 0)
        metrics["borrowings"] = {"latest": borrow_latest, "prev": borrows[1]}
        metrics["debt_to_equity"] = round(borrow_latest / equity_total, 2) if (borrow_latest and equity_total) else (0.0 if borrow_latest == 0 else None)

        cfo_row, _ = (self._annual_series(cf, ("Cash from Operating Activity", "Cash from Operations")) if cf else ([], None))
        cfo = self._latest_prev(cfo_row)
        fcf_row, _ = (self._annual_series(cf, ("Free Cash Flow",)) if cf else ([], None))
        fcf = self._latest_prev(fcf_row)
        metrics["cfo"] = {"latest": cfo[0], "prev": cfo[1]}
        metrics["free_cash_flow"] = {"latest": fcf[0], "prev": fcf[1]}
        if npv[0] and cfo[0] is not None:
            metrics["cfo_to_pat"] = round(cfo[0] / npv[0], 2)

        ccc_row, _ = (self._annual_series(ratios, ("Cash Conversion Cycle",)) if ratios else ([], None))
        ccc = self._latest_prev(ccc_row)
        metrics["cash_conversion_cycle"] = {"latest": ccc[0], "prev": ccc[1]}
        roce_row, _ = (self._annual_series(ratios, ("ROCE %", "Return on Capital Employed %")) if ratios else ([], None))
        roce_ann = self._latest_prev(roce_row)
        metrics["roce_annual"] = {"latest": roce_ann[0], "prev": roce_ann[1]}

        prom_row, _ = (self._annual_series(share, ("Promoters",)) if share else ([], None))
        prom = self._latest_prev(prom_row)
        metrics["promoter_holding"] = {"latest": prom[0], "prev": prom[1]}

        metrics["quarters"] = self._quarter_momentum(quarters, ("Sales", "Revenue"), "Net Profit")

        top_map = {}
        for k, v in top.items():
            clean = k.replace("\xa0", " ").strip()
            top_map[clean] = v["nums"][0] if v["nums"] else None

        price = top_map.get("Current Price")
        mcap = top_map.get("Market Cap")
        pe = top_map.get("Stock P/E")
        book = top_map.get("Book Value")
        div_yield = top_map.get("Dividend Yield")
        roce = top_map.get("ROCE")
        roe = top_map.get("ROE")
        face = top_map.get("Face Value")

        header = {
            "name": name, "price": price, "market_cap_cr": mcap,
            "pe": pe, "book_value": book, "dividend_yield": div_yield,
            "roce": roce, "roe": roe, "face_value": face,
            "sector": sector, "industry": industry,
        }

        good, problems, quality, verdict, watch, risk = self._build_analysis(header, metrics)

        data = {
            "ticker": ticker.upper(), "name": name, "source": "screener.in",
            "available": True,
            "header": header,
            "metrics": metrics,
            "the_good": good,
            "the_problems": problems,
            "earnings_quality": quality,
            "verdict": verdict,
            "watch": watch,
            "risk_level": risk,
            "disclaimer": ("Data extracted from screener.in (public financials). "
                           "Not investment advice — automated snapshot; do your own research."),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._store(symbol, data)
        return data

    def _pct(self, v: float | None, signed: bool = False) -> str | None:
        if v is None:
            return None
        if signed and v > 0:
            return f"+{v:.1f}%"
        return f"{v:.1f}%"

    def _build_analysis(self, header: dict, m: dict) -> tuple:
        name = header.get("name") or header.get("price") and "Company" or ""
        price = header.get("price")
        mcap = header.get("market_cap_cr")
        pe = header.get("pe")
        roce = header.get("roce")
        roe = header.get("roe")
        book = header.get("book_value")
        div_yield = header.get("dividend_yield")

        rev = m.get("revenue") or {}
        np = m.get("net_profit") or {}
        opm = m.get("opm") or {}
        nm = m.get("net_margin")
        cfo = m.get("cfo") or {}
        fcf = m.get("free_cash_flow") or {}
        ccc = m.get("cash_conversion_cycle") or {}
        borrow = m.get("borrowings") or {}
        d2e = m.get("debt_to_equity")
        prom = m.get("promoter_holding") or {}
        cfo_pat = m.get("cfo_to_pat")
        quarters = m.get("quarters") or []
        roce_ann = (m.get("roce_annual") or {}).get("latest")

        price_str = f"₹{price:,.2f}" if price is not None else None
        mcap_str = f"₹{mcap:,.0f} Cr" if mcap is not None else None

        good: list[str] = []
        problems: list[str] = []
        quality_lines: list[str] = []

        rev_growth = rev.get("growth")
        rev_cagr = rev.get("cagr")
        np_growth = np.get("growth")
        latest_rev = rev.get("latest")
        prev_rev = rev.get("prev")
        latest_np = np.get("latest")
        prev_np = np.get("prev")
        ttm_np = np.get("ttm")
        latest_opm = opm.get("latest")
        prev_opm = opm.get("prev")
        ttm_opm = opm.get("ttm")

        if latest_rev is not None:
            now_str = f"₹{latest_rev:,.0f} Cr" if latest_rev >= 1 else f"₹{latest_rev * 100:,.0f} L"
            prev_str = f"₹{prev_rev:,.0f} Cr" if (prev_rev or 0) >= 1 else f"₹{(prev_rev or 0) * 100:,.0f} L"
            if rev_growth is not None and rev_growth > 20:
                good.append(f"Revenue growth is solid — latest year {now_str} vs {prev_str} ({self._pct(rev_growth, True)} YoY).")
            elif rev_growth is not None and rev_growth >= 5:
                good.append(f"Revenue is growing steadily — latest year {now_str} vs {prev_str} ({self._pct(rev_growth, True)} YoY).")
            elif rev_growth is not None and 0 <= rev_growth < 5:
                good.append(f"Revenue is roughly flat — latest year {now_str} ({self._pct(rev_growth, True)} YoY).")
            elif rev_growth is not None and rev_growth < 0:
                problems.append(f"Revenue is shrinking — latest year {now_str} vs {prev_str} ({self._pct(rev_growth)} YoY).")
            else:
                good.append(f"Revenue at {now_str} for the latest year.")
            if rev_cagr is not None and rev_cagr > 15 and (rev_growth is None or rev_growth >= -5):
                good.append(f"Multi-year sales CAGR is ~{self._pct(rev_cagr)} — a durable growth story, not a one-off.")

        if latest_np is not None:
            if latest_np < 0:
                if prev_np and latest_np > prev_np:
                    problems.append(f"Still loss-making: net loss narrowed to ₹{latest_np:,.1f} Cr "
                                    f"from ₹{prev_np:,.1f} Cr — positive step, but no profits yet.")
                else:
                    problems.append(f"Loss-making with net loss at ₹{latest_np:,.1f} Cr"
                                    + (f" (vs ₹{prev_np:,.1f} Cr last year)" if prev_np is not None else "")
                                    + " — the business is burning cash at the profit line.")
            elif prev_np and latest_np > prev_np:
                good.append(f"Profits improved to ₹{latest_np:,.1f} Cr from ₹{prev_np:,.1f} Cr "
                            f"({self._pct(np_growth, True)} YoY).")
            elif prev_np and latest_np < prev_np:
                problems.append(f"Profit fell to ₹{latest_np:,.1f} Cr from ₹{prev_np:,.1f} Cr "
                                f"({self._pct(np_growth)} YoY) — earnings are decelerating, not growing.")
            elif not prev_np:
                good.append(f"Profitable at ₹{latest_np:,.1f} Cr net profit.")
            if nm is not None and nm > 10:
                good.append(f"Healthy net margin at ~{nm:.1f}% — the business converts sales to profit efficiently.")

        if latest_opm is not None:
            if latest_opm < -50:
                problems.append("Deeply loss-making at the operating level (OPM "
                                f"{max(latest_opm, -100):.0f}%) — cash burn is structural, not a margin squeeze.")
            elif latest_opm < 0:
                problems.append(f"Operating loss of ~{max(latest_opm, -50):.1f}% margin — the core business does not "
                                "yet pay for itself; survival depends on scale and funding.")
            elif latest_opm < 8:
                problems.append(f"Very thin operating margin (~{latest_opm:.1f}%"
                                + (f", TTM {ttm_opm:.1f}%" if ttm_opm is not None else "")
                                + ") — this is a low-moat / low-margin business, not a high-return franchise.")
            elif latest_opm < 12:
                good.append(f"Decent operating margin at ~{latest_opm:.1f}%.")
            else:
                good.append(f"Strong operating margin at ~{latest_opm:.1f}%.")
            if prev_opm is not None and ttm_opm is not None and ttm_opm < prev_opm and latest_opm >= -50:
                decline_str = f"OPM fell from {prev_opm:.1f}% to {latest_opm:.1f}% and TTM is {ttm_opm:.1f}%,"
                if latest_opm < 10:
                    problems.append("Margins are trending down — " + decline_str +
                                    " so recent expansion/higher costs are not translating into profitability.")
                elif ttm_opm < prev_opm - 2:
                    problems.append("Margins have slipped — " + decline_str +
                                    " watch whether this is mix, pricing or one-off costs.")

        if pe is not None:
            if roe and pe > 35 and roe < 12:
                problems.append(f"Rich valuation: P/E ~{pe:.1f}x on a business with ROE ~{roe:.1f}% — "
                                "you are paying a premium for modest returns.")
            elif pe > 50:
                problems.append(f"Very expensive at ~{pe:.1f}x trailing earnings.")
            elif pe is not None and pe <= 20:
                good.append(f"Reasonable valuation at ~{pe:.1f}x trailing earnings.")
        if roe is not None:
            if roe >= 15:
                good.append(f"High return on equity (~{roe:.1f}%) — capital is being deployed well.")
            elif roe < 8:
                problems.append(f"Weak returns — ROE only ~{roe:.1f}% (ROCE ~{roce:.1f}% if available). "
                                "Value creation per rupee of equity is low.")
        if div_yield and div_yield > 1.5:
            good.append(f"Decent dividend yield of ~{div_yield:.2f}% for income support.")
        elif price and book and price / book > 5:
            problems.append(f"Price-to-book is elevated (~{price / book:.1f}x) — a lot is priced in beyond assets.")

        prom_latest = prom.get("latest")
        if prom_latest is not None:
            if prom_latest >= 50:
                good.append(f"Promoter holding is solid at ~{prom_latest:.1f}% — aligned with minority shareholders.")
            elif prom_latest < 35:
                problems.append(f"Promoter holding is low at ~{prom_latest:.1f}%.")

        cfo_latest = cfo.get("latest")
        if cfo_latest is not None and latest_np is not None and latest_np > 0:
            if cfo_pat is not None and cfo_pat >= 0.8:
                good.append("Cash flow supports reported profit — CFO/PAT "
                            f"~{cfo_pat:.2f}x, so earnings are 'real' cash.")
            elif cfo_pat is not None and cfo_pat < 0.3:
                problems.append("Weak earnings quality — cash from operations covers only "
                                f"{cfo_pat * 100:.0f}% of reported profit; profits are on paper, not in the bank.")
            elif cfo_latest < 0:
                problems.append(f"Profits do not match cash — the company is profitable on paper "
                                f"but consumed ₹{abs(cfo_latest):,.1f} Cr of cash in operations.")
        elif cfo_latest is not None and cfo_latest < 0 and latest_np is not None and latest_np < 0:
            problems.append(f"Cash burn continues — operating cash flow is ₹{cfo_latest:,.1f} Cr "
                            "negative; funding is needed to keep the business running.")
        ccc_latest = ccc.get("latest")
        if ccc_latest is not None:
            if ccc_latest > 60:
                problems.append(f"Cash gets locked in the cycle — cash conversion cycle ~{ccc_latest:.0f} days "
                                "tied up in inventory/receivables.")
            elif ccc_latest <= 30:
                good.append(f"Tight working capital — cash conversion cycle only ~{ccc_latest:.0f} days.")
        if d2e is not None:
            if d2e == 0:
                good.append("Debt-free balance sheet.")
            elif d2e < 0.5:
                good.append(f"Comfortable leverage — debt/equity ~{d2e:.2f}.")
            elif d2e > 1.5:
                problems.append(f"Heavy leverage — debt/equity ~{d2e:.2f} raises risk in a downturn.")
        else:
            bl = borrow.get("latest")
            if bl and bl > 0 and (latest_np or 0) and bl / max(latest_np, 1) > 5:
                problems.append(f"Borrowings (₹{bl:,.0f} Cr) are large vs annual profit (₹{latest_np:,.0f} Cr).")

        q = [q for q in quarters if q.get("net_profit") is not None]
        if len(q) >= 5:
            recent = q[-1]["net_profit"]
            yr_ago = q[-5]["net_profit"]
            recent_sales = q[-1].get("sales")
            yr_ago_sales = q[-5].get("sales")
            if yr_ago and recent < yr_ago:
                problems.append(f"Recent quarters confirm the downtrend — latest quarter net profit ₹{recent:,.2f} Cr "
                                f"vs ₹{yr_ago:,.2f} Cr a year ago"
                                + (f"; sales ₹{recent_sales:,.1f} Cr vs ₹{yr_ago_sales:,.1f} Cr"
                                   if recent_sales is not None and yr_ago_sales else "")
                                + ".")
            elif yr_ago and recent > yr_ago:
                good.append(f"Momentum intact — latest quarter net profit ₹{recent:,.2f} Cr "
                            f"vs ₹{yr_ago:,.2f} Cr a year ago.")

        if not good and not problems:
            good.append("Fundamentals appear stable based on available screener.in data.")

        if not problems:
            quality_lines.append("Overall financial quality looks solid on the data available — "
                                 "decent margins/returns, cash flow and leverage within comfort.")
        else:
            quality_lines.append("Mixed quality — the strengths above are offset by the "
                                 f"{'valuation' if pe and pe > 25 else 'earnings momentum'} "
                                 "and margin concerns listed.")

        verdict = self._make_verdict(header, m, good, problems)
        watch = self._make_watch(header, m)
        risk = self._risk_level(header, m, len(problems))
        return good, problems, quality_lines, verdict, watch, risk

    def _make_verdict(self, header: dict, m: dict, good: list, problems: list) -> str:
        np = m.get("net_profit") or {}
        rev = m.get("revenue") or {}
        opm = m.get("opm") or {}
        pe = header.get("pe")
        mcap = header.get("market_cap_cr")
        latest_np = np.get("latest")
        ttm_np = np.get("ttm")
        latest_opm = opm.get("latest")

        growth = rev.get("growth")
        np_growth = np.get("growth")
        weak_momentum = (growth is not None and growth < 0) or (np_growth is not None and np_growth < 0)
        n_problem = len(problems)
        n_good = len(good)

        size = "small-cap" if mcap and mcap < 10000 else "mid/large-cap"
        profit_text = f"{ttm_np or latest_np:,.1f} Cr" if (ttm_np or latest_np) else "modest"

        if n_problem >= 4 and weak_momentum and n_problem > n_good:
            v = (f"The numbers tell a cautionary story: a {size} with {profit_text} profit is not "
                 + "a compelling fundamentals buy "
                 + (f"at ~{pe:.1f}x earnings" if pe else "at current valuations")
                 + " when growth and margins are under pressure. "
                 "It behaves more like a story/momentum idea right now than a value compounder.")
        elif n_problem == 0 or (n_good >= 6 and n_problem <= 1):
            v = (f"A fundamentally attractive {size} — the balance sheet and profit engine are solid "
                 + (f"({self._pct(growth, True)} sales growth" if growth is not None else "with steady sales")
                 + "), earnings quality is good and there are no major red flags on the screener data. "
                 "Suitable for a core position; re-verify quarterly as valuations move.")
        elif n_problem >= 4 and n_good < n_problem:
            v = (f"A weak setup for this {size} right now — more negatives than positives on "
                 "the screener data (margins, momentum, cash flow or leverage). "
                 "Not a fundamentals buy at this price; prefer quality names with growing margins.")
        else:
            v = (f"A mixed picture for this {size}. There is a real growth/liquidity story "
                 + (f"({self._pct(growth, True)} sales growth" if growth is not None else "(with growth")
                 + "), but the weaknesses mean it is not a high-conviction fundamentals buy at this price. "
                 "Treat as high-risk and size positions accordingly.")
        return v

    def _make_watch(self, header: dict, m: dict) -> str:
        opm = m.get("opm") or {}
        lines = ["Watch operating margin (target improving toward 7-8%+ for a low-margin business),",
                 "the next 2-3 quarters of profit growth (positive before calling it a trend change),",
                 "and working capital / cash conversion — an improving cycle plus rising CFO confirms the story."]
        return " ".join(lines)

    def _risk_level(self, header: dict, m: dict, problem_count: int) -> str:
        mcap = header.get("market_cap_cr")
        pe = header.get("pe")
        risk = "Low"
        if mcap is not None and mcap < 1000:
            risk = "High"
        elif mcap is not None and mcap < 5000:
            risk = "Medium-High"
        elif pe and pe > 40:
            risk = "Medium-High"
        if problem_count >= 4:
            risk = "High"
        elif problem_count >= 3 and risk == "Low":
            risk = "Medium"
        return risk


fundamental_analyzer = FundamentalAnalyzer()