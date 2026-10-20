const API_BASE = "";
let currentFilter = { segment: null, direction: null };

async function fetchAPI(endpoint, timeoutMs = 15000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        const resp = await fetch(API_BASE + endpoint, { signal: ctrl.signal });
        if (!resp.ok) throw new Error("API error: " + resp.status);
        return resp.json();
    } finally {
        clearTimeout(timer);
    }
}

async function fetchAPI_JSON(endpoint, method, body, timeoutMs = 15000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
        const resp = await fetch(API_BASE + endpoint, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: body ? JSON.stringify(body) : undefined,
            signal: ctrl.signal,
        });
        if (!resp.ok) {
            var msg = "API error: " + resp.status;
            try { var d = await resp.json(); if (d.error) msg = d.error; } catch (e) {}
            throw new Error(msg);
        }
        return resp.json();
    } finally {
        clearTimeout(timer);
    }
}

function escapeHtml(str) {
    return String(str == null ? "" : str)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function formatPrice(val) {
    if (val == null || isNaN(val)) return "\u2014";
    return "\u20B9" + Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function getPage() {
    var path = window.location.pathname;
    if (path === "/" || path === "") return "dashboard";
    var p = path.replace("/", "").split("/")[0].split("?")[0].split("#")[0];
    var pages = ["chart", "news", "journal", "sectors", "flows", "breadth", "seasonal", "stocks", "portfolio"];
    return pages.indexOf(p) !== -1 ? p : "dashboard";
}

/* ─────── Market Overview (shared) ─────── */
function renderOverview(overview) {
    const els = document.querySelectorAll(".market-status");
    if (!els.length) return;
    els.forEach(function (el) {
        var statusClass = (overview.market_status || "closed").toLowerCase().replace(" ", "-");
        var dot = el.querySelector(".status-dot");
        if (dot) dot.className = "status-dot " + statusClass;
        var label = el.querySelector("span:last-child");
        if (label) {
            var labels = {
                open: "Market Open", closed: "Market Closed", weekend: "Weekend \u2014 Closed",
                holiday: "Holiday \u2014 Closed", "pre-market": "Pre-Market", "post-market": "Post-Market",
            };
            label.textContent = labels[statusClass] || overview.market_status || "\u2014";
        }
    });
    var niftyEl = document.getElementById("nifty-value");
    if (niftyEl) niftyEl.textContent = overview.nifty_50 ? formatPrice(overview.nifty_50) : "\u2014";
    var changeEl = document.getElementById("nifty-change");
    if (changeEl && overview.nifty_change_pct != null) {
        var cls = overview.nifty_change_pct >= 0 ? "positive" : "negative";
        changeEl.textContent = (overview.nifty_change_pct >= 0 ? "+" : "") + overview.nifty_change_pct.toFixed(2) + "%";
        changeEl.className = "overview-value " + cls;
    }
    var bnEl = document.getElementById("banknifty-value");
    if (bnEl) bnEl.textContent = overview.bank_nifty ? formatPrice(overview.bank_nifty) : "\u2014";
    var updEl = document.getElementById("last-updated");
    if (updEl) updEl.textContent = "Updated: " + (overview.last_updated || "\u2014");
}

async function loadOverview() {
    try { renderOverview(await fetchAPI("/api/overview")); }
    catch (e) { /* silent */ }
}

/* ─────── Signal Cards (dashboard) ─────── */
function renderInsightBar(signal) {
    var upside = signal.upside_pct, downside = signal.downside_pct;
    if (upside == null) return "";
    var dir = (signal.direction || "").toLowerCase();
    var isBearish = dir === "bearish";
    var downSafe = (downside != null && downside > 0) ? downside : 0;
    var gaugePct = downSafe > 0 ? Math.min((upside / (upside + downSafe)) * 100, 90) : 90;
    var profitLabel = isBearish ? "Profit" : "Upside";
    var riskLabel = isBearish ? "Risk" : "Downside";
    var profitVal = '+' + upside + '%';
    var riskVal = downSafe > 0 ? downSafe + '%' : "\u2014";
    return '<div class="insight-bar">'
        + '<div class="insight-item"><span class="insight-label">' + profitLabel + '</span><span class="insight-value positive">' + profitVal + '</span></div>'
        + '<div class="insight-item" style="flex:1;"><div class="insight-gauge"><div class="insight-gauge-fill upside" style="width:' + gaugePct + '%;"></div></div></div>'
        + '<div class="insight-item"><span class="insight-label">' + riskLabel + '</span><span class="insight-value negative">-' + riskVal + '</span></div>'
        + '<div class="rr-badge">R:R ' + signal.rr_ratio + '</div>'
        + '</div>';
}

function renderSignalCard(signal) {
    var dirClass = (signal.direction || "").toLowerCase();
    var isBuy = signal.action === "BUY";
    var isShort = signal.action === "SHORT SELL";
    var badgeBg = isBuy ? "#16a34a" : isShort ? "#dc2626" : "#64748b";
    var badgeText = isBuy ? "BUY" : isShort ? "SHORT SELL" : (signal.action || "HOLD");
    var segClass = (signal.segment || "").toLowerCase().replace(" ", "-");
    var segBadge = '<span class="signal-badge ' + segClass + '">' + signal.segment + '</span>';
    var t2Val = signal.target_2 ? formatPrice(signal.target_2) : "Trail";
    var html = '<div class="signal-card ' + dirClass + '" data-ticker="' + signal.ticker + '" onclick="openChartFromSignal(this)" style="cursor:pointer;">'
        + '<div class="signal-header">'
        + '<div><div class="signal-ticker">' + signal.ticker + '</div>'
        + '<div class="signal-direction ' + dirClass + '"><span style="display:inline-block;background:' + badgeBg + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;letter-spacing:0.5px;margin-right:6px;">' + badgeText + '</span>' + (signal.direction || "") + '</div></div>'
        + '<div style="display:flex;align-items:center;gap:0.5rem;">'
        + buttonAdd(signal)
        + segBadge
        + '</div>'
        + '</div>'
        + '<div class="signal-details">'
        + '<div class="detail-item"><span class="detail-label">LTP</span><span class="detail-value" style="font-weight:700;color:#3b82f6;">' + formatPrice(signal.current_price) + '</span></div>'
        + '<div class="detail-item"><span class="detail-label">Entry</span><span class="detail-value">' + formatPrice(signal.entry_price) + '</span></div>'
        + '<div class="detail-item"><span class="detail-label">Range</span><span class="detail-value">' + formatPrice(signal.entry_range_low) + ' \u2014 ' + formatPrice(signal.entry_range_high) + '</span></div>'
        + '<div class="detail-item"><span class="detail-label">Target 1</span><span class="detail-value" style="color:#22c55e;">' + formatPrice(signal.target_1) + '</span></div>'
        + '<div class="detail-item"><span class="detail-label">Target 2</span><span class="detail-value" style="color:#22c55e;">' + t2Val + '</span></div>'
        + '<div class="detail-item"><span class="detail-label">Stop Loss</span><span class="detail-value" style="color:#ef4444;">' + formatPrice(signal.stop_loss) + '</span></div>'
        + '<div class="detail-item"><span class="detail-label">Exit</span><span class="detail-value">' + (signal.exit_time || "\u2014") + '</span></div>'
        + '</div>'
        + renderInsightBar(signal);
    if (signal.chart_note) {
        html += '<div style="font-size:12px;color:#94a3b8;margin-top:8px;padding:6px 10px;background:#0a0e17;border-radius:6px;border-left:2px solid #3b82f6;">' + signal.chart_note + '</div>';
    }
    if (signal.disclaimer) {
        html += '<div style="font-size:11px;color:#fbbf24;margin-top:6px;padding:6px 10px;background:#1c1505;border-radius:6px;border-left:2px solid #f59e0b;">&#9888; ' + signal.disclaimer + '</div>';
    }
    html += '<div class="signal-strategy">' + signal.strategy_name + ' | ' + (signal.entry_timestamp || "") + '</div>'
        + '<div class="confidence-bar"><div class="confidence-fill" style="width:' + (signal.confidence || 0) + '%;"></div></div>'
        + '</div>';
    return html;
}

function buttonAdd(signal) {
    var t = signal.ticker || "";
    var entry = signal.entry_price != null ? signal.entry_price : "";
    var stop = signal.stop_loss != null ? signal.stop_loss : "";
    var seg = signal.segment || "MISC";
    return '<button class="btn btn-sm" data-ticker="' + t + '" style="padding:3px 9px;font-size:0.7rem;" '
        + 'onclick="event.stopPropagation(); addSignalToPortfolio(\'' + t + '\',' + entry + ',' + stop + ',\'' + seg + '\');" '
        + 'title="Add to Portfolio">+ Add</button>';
}

function openChartFromSignal(el) {
    var t = el.getAttribute("data-ticker");
    if (t) window.location.href = "/chart?ticker=" + t;
}

async function addSignalToPortfolio(ticker, entryPrice, stopLoss, segment) {
    var qty = parseFloat(window.prompt("Enter quantity to buy of " + ticker + ":", "1"));
    if (!qty || isNaN(qty) || qty <= 0) return;
    try {
        await fetchAPI_JSON("/api/portfolio", "POST", {
            ticker: ticker,
            qty: qty,
            avg_price: entryPrice || undefined,
            stop_loss: stopLoss || undefined,
            segment: segment || "MISC",
            buy_date: new Date().toISOString().slice(0, 10),
        });
        alert(ticker + " added to portfolio.");
    } catch (e) {
        alert("Failed to add: " + e.message);
    }
}

async function loadSignals() {
    var container = document.getElementById("signals-container");
    if (!container) return;
    if (window._signalsTimer) { clearTimeout(window._signalsTimer); window._signalsTimer = null; }
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading signals...</p></div>';
    try {
        var url = "/api/signals";
        var params = [];
        if (currentFilter.segment) params.push("segment=" + currentFilter.segment);
        if (currentFilter.direction) params.push("direction=" + currentFilter.direction);
        if (params.length) url += "?" + params.join("&");
        var result = await fetchAPI(url, 300000);
        if (result.scanning) {
            container.innerHTML = '<div class="empty-state"><h3>Scan In Progress</h3><p>Market scan is running in the background (can take 1\u20133 minutes on first load). This page will auto-refresh when it completes.</p><button class="btn btn-primary" onclick="loadSignals()" style="margin-top:1rem;">Check Again</button></div>';
            var sc = document.getElementById("signal-count");
            if (sc) sc.textContent = "\u2026";
            window._signalsTimer = setTimeout(function () {
                var still = document.getElementById("signals-container");
                window._signalsTimer = null;
                if (still && still.querySelector(".empty-state") && currentFilter) loadSignals();
            }, 30000);
            return;
        }
        if (!result.signals || result.signals.length === 0) {
            container.innerHTML = '<div class="empty-state"><h3>No Signals Generated</h3><p>No trading signals detected. Market may be closed or no setups met criteria. During PRE-MARKET / CLOSED hours, Intraday signals are not generated (they need live intraday bars).</p><button class="btn btn-primary" onclick="loadSignals()" style="margin-top:1rem;">Refresh Scan</button></div>';
            var sc = document.getElementById("signal-count");
            if (sc) sc.textContent = "0";
            return;
        }
        container.innerHTML = result.signals.map(renderSignalCard).join("");
        var sc = document.getElementById("signal-count");
        if (sc) sc.textContent = result.signals.length;
        var ls = document.getElementById("last-scan");
        if (ls) ls.textContent = "Last scan: " + result.scan_timestamp;
    } catch (err) {
        container.innerHTML = '<div class="empty-state"><h3>Error Loading Signals</h3><p>' + err.message + '</p><button class="btn btn-primary" onclick="loadSignals()" style="margin-top:1rem;">Retry</button></div>';
    }
}

function getSegmentBadge(seg) {
    var cls = (seg || "").toLowerCase().replace(" ", "-");
    return '<span class="signal-badge ' + cls + '">' + seg + '</span>';
}

/* ─────── Chart Analysis (chart page + embedded) ─────── */
async function loadChartAnalysis(ticker) {
    var container = document.getElementById("chart-result");
    if (!container) return;
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p>Analyzing ' + ticker + '...</p></div>';
    try {
        var ta = await fetchAPI("/api/chart-analysis?ticker=" + ticker, 120000);
        if (ta.data_available === false) {
            container.innerHTML = '<div class="empty-state"><h3>Data Unavailable</h3><p>' + (ta.recommendation || "No data available") + ' for ' + ta.ticker + '. yfinance could not retrieve quotes/history — no fabricated data is shown.</p></div>';
            return;
        }
        var planHtml = ta.signal ? signalPlanHTML(ta.signal) : "";
        var supportList = (ta.support && ta.support.length) ? ta.support : ["\u2014", "\u2014"];
        var resistanceList = (ta.resistance && ta.resistance.length) ? ta.resistance : ["\u2014", "\u2014"];
        var trendColor = ta.trend === "BULLISH" ? "#22c55e" : ta.trend === "BEARISH" ? "#ef4444" : "#94a3b8";
        var trendBg = ta.trend === "BULLISH" ? "rgba(34,197,94,0.15)" : ta.trend === "BEARISH" ? "rgba(239,68,68,0.15)" : "rgba(148,163,184,0.15)";
        var rsiIcon = ta.rsi > 60 ? "\uD83D\uDD25" : ta.rsi < 40 ? "\u2744\uFE0F" : "\u27A1\uFE0F";
        var html = planHtml
            + '<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:1.25rem;">'
            + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">'
            + '<h3 style="font-size:1.1rem;font-weight:700;margin:0;">' + ta.ticker + ' <span style="font-size:0.85rem;font-weight:400;color:var(--text-secondary);">' + formatPrice(ta.last_price) + '</span></h3>'
            + '<span style="padding:0.25rem 0.75rem;border-radius:20px;font-size:0.7rem;font-weight:700;background:' + trendBg + ';color:' + trendColor + ';">' + ta.trend + '</span>'
            + '</div>'
            + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:0.5rem;margin-bottom:0.75rem;">'
            + '<div><div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">RSI</div><div style="font-size:0.9rem;font-weight:600;">' + ta.rsi + ' ' + rsiIcon + '</div></div>'
            + '<div><div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">MACD</div><div style="font-size:0.9rem;font-weight:600;">' + ta.macd + '</div></div>'
            + '<div><div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">Volume</div><div style="font-size:0.9rem;font-weight:600;">' + ta.volume_analysis + '</div></div>'
            + '<div><div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">Pattern</div><div style="font-size:0.9rem;font-weight:600;">' + (ta.pattern || "\u2014") + '</div></div>'
            + '</div>'
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:0.75rem;">'
            + '<div style="padding:0.5rem;background:var(--bg-primary);border-radius:6px;border-left:2px solid #22c55e;"><div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">Support</div><div style="font-size:0.85rem;font-weight:600;">' + formatPrice(supportList[0]) + ' \u2192 ' + formatPrice(supportList[1]) + '</div></div>'
            + '<div style="padding:0.5rem;background:var(--bg-primary);border-radius:6px;border-left:2px solid #ef4444;"><div style="font-size:0.65rem;color:var(--text-muted);text-transform:uppercase;">Resistance</div><div style="font-size:0.85rem;font-weight:600;">' + formatPrice(resistanceList[0]) + ' \u2192 ' + formatPrice(resistanceList[1]) + '</div></div>'
            + '</div>'
            + '<div style="padding:0.5rem 0.75rem;border-radius:6px;background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.2);font-size:0.85rem;font-weight:600;color:#3b82f6;">' + ta.recommendation + '</div>'
            + '<div class="confidence-bar" style="margin-top:0.75rem;"><div class="confidence-fill" style="width:' + ta.confidence + '%;"></div></div>'
            + '</div>';
        container.innerHTML = html;
        loadFundamentalAnalysis(ticker);
    } catch (err) {
        container.innerHTML = '<div class="empty-state"><h3>Error</h3><p>' + err.message + '</p></div>';
    }
}

async function loadFundamentalAnalysis(ticker) {
    var container = document.getElementById("chart-result");
    if (!container) return;
    var fundDiv = document.createElement("div");
    fundDiv.id = "fundamental-result";
    fundDiv.style.cssText = "margin-top:1rem;";
    fundDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading fundamentals from screener.in...</p></div>';
    container.appendChild(fundDiv);
    try {
        var f = await fetchAPI("/api/fundamental?ticker=" + ticker, 45000);
        if (f.available === false) {
            fundDiv.innerHTML = '<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:1.25rem;">'
                + '<h3 style="font-size:1.1rem;font-weight:700;margin:0 0 0.5rem;">Fundamental Analysis</h3>'
                + '<div class="empty-state" style="padding:0.5rem 0;"><p>' + escapeHtml(f.error || "Fundamentals unavailable") + '</p></div></div>';
            return;
        }
        fundDiv.innerHTML = fundamentalHTML(f);
    } catch (err) {
        fundDiv.innerHTML = '<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:1.25rem;">'
            + '<h3 style="font-size:1.1rem;font-weight:700;margin:0 0 0.5rem;">Fundamental Analysis</h3>'
            + '<div class="empty-state" style="padding:0.5rem 0;"><p>' + escapeHtml(err.message) + '</p></div></div>';
    }
}

function fmtCr(v) {
    if (v == null || isNaN(v)) return "\u2014";
    return "\u20B9" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " Cr";
}

function fmtPct(v, signed) {
    if (v == null || isNaN(v)) return "\u2014";
    var s = Number(v).toFixed(2) + "%";
    if (signed && v > 0) s = "+" + s;
    return s;
}

function fmtPctClamped(v, signed) {
    if (v == null || isNaN(v)) return "\u2014";
    var n = Number(v);
    if (Math.abs(n) > 300) return n < 0 ? "loss-making" : "N/A";
    return fmtPct(n, signed);
}

function valChip(label, value, color) {
    var c = color || "var(--text-primary)";
    return '<div style="padding:0.45rem 0.6rem;background:var(--bg-primary);border-radius:6px;border:1px solid var(--border-color);">'
        + '<div style="font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:2px;">' + label + '</div>'
        + '<div style="font-size:0.85rem;font-weight:600;color:' + c + ';">' + value + '</div></div>';
}

function fundamentalHTML(f) {
    var h = f.header || {};
    var m = f.metrics || {};
    var rev = m.revenue || {};
    var np = m.net_profit || {};
    var opm = m.opm || {};
    var qr = m.quarters || [];

    var revChip = valChip("Revenue\u00b7Latest", fmtCr(rev.latest), "#3b82f6");
    var revYoY = valChip("Revenue\u00b7YoY", fmtPct(rev.growth, true), rev.growth >= 0 ? "#22c55e" : "#ef4444");
    var revCagr = valChip("Sales CAGR", fmtPct(rev.cagr), rev.cagr >= 0 ? "#22c55e" : "#ef4444");
    var npChip = valChip("Net Profit\u00b7Latest", fmtCr(np.latest), "#3b82f6");
    var npYoY = valChip("Profit\u00b7YoY", fmtPct(np.growth, true), (np.growth || 0) >= 0 ? "#22c55e" : "#ef4444");
    var npTtm = valChip("Profit\u00b7TTM", fmtCr(np.ttm), "#3b82f6");
    var opmChip = valChip("OPM\u00b7Latest", (opm.latest == null || isNaN(opm.latest)) ? "\u2014" : (Math.abs(opm.latest) > 300 ? (opm.latest < 0 ? "loss-making" : "N/A") : opm.latest.toFixed(1) + "%"), opm.latest < 0 ? "#ef4444" : "#f59e0b");
    var nmChip = valChip("Net Margin", fmtPctClamped(m.net_margin), (m.net_margin || 0) < 0 ? "#ef4444" : "#f59e0b");
    var peChip = valChip("P/E", (h.pe == null ? "\u2014" : "~" + h.pe.toFixed(1) + "x"), h.pe > 40 ? "#ef4444" : "#22c55e");
    var mcapChip = valChip("Mkt Cap", fmtCr(h.market_cap_cr), "#3b82f6");
    var roeChip = valChip("ROE", fmtPct(h.roe), (h.roe || 0) >= 12 ? "#22c55e" : "#ef4444");
    var roceChip = valChip("ROCE", fmtPct(h.roce), (h.roce || 0) >= 12 ? "#22c55e" : "#ef4444");
    var debtChip = valChip("D/E", m.debt_to_equity == null ? "\u2014" : m.debt_to_equity.toFixed(2), "#f59e0b");
    var promChip = valChip("Promoters", fmtPct(m.promoter_holding && m.promoter_holding.latest), (m.promoter_holding && m.promoter_holding.latest || 0) >= 50 ? "#22c55e" : "#ef4444");
    var cccChip = valChip("Cash Conv. Cycle", ((m.cash_conversion_cycle && m.cash_conversion_cycle.latest) == null ? "\u2014" : m.cash_conversion_cycle.latest.toFixed(0) + " days"), "#f59e0b");
    var cfoChip = valChip("CFO/PAT", m.cfo_to_pat == null ? "\u2014" : "~" + m.cfo_to_pat.toFixed(2) + "x", (m.cfo_to_pat || 0) >= 0.8 ? "#22c55e" : "#ef4444");

    var riskColor = f.risk_level === "High" ? "#ef4444" : f.risk_level === "Medium" ? "#f59e0b" : "#22c55e";
    var riskBg = f.risk_level === "High" ? "rgba(239,68,68,0.12)" : f.risk_level === "Medium" ? "rgba(245,158,11,0.12)" : "rgba(34,197,94,0.12)";

    var goodHtml = (f.the_good || []).map(function (g) {
        return '<div style="display:flex;gap:0.5rem;padding:0.35rem 0;"><span style="color:#22c55e;font-weight:700;">\u2713</span><span>' + escapeHtml(g) + '</span></div>';
    }).join("") || '<div style="padding:0.35rem 0;color:var(--text-muted);">No stand-out strengths detected on the data.</div>';

    var problemHtml = (f.the_problems || []).map(function (p) {
        return '<div style="display:flex;gap:0.5rem;padding:0.35rem 0;"><span style="color:#ef4444;font-weight:700;">\u26A0</span><span>' + escapeHtml(p) + '</span></div>';
    }).join("") || '<div style="padding:0.35rem 0;color:var(--text-muted);">No major red flags detected.</div>';

    var qualityHtml = (f.earnings_quality || []).map(function (q) {
        return '<div style="padding:0.35rem 0;">' + escapeHtml(q) + '</div>';
    }).join("");

    var quarterRows = "";
    qr.slice(-6).forEach(function (q) {
        quarterRows += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.4rem;padding:0.35rem 0;border-top:1px solid var(--border-color);font-size:0.8rem;">'
            + '<span style="color:var(--text-secondary);">' + escapeHtml(q.q) + '</span>'
            + '<span>' + (q.sales == null ? "\u2014" : "\u20B9" + q.sales.toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " Cr") + '</span>'
            + '<span style="color:' + (q.net_profit >= 0 ? "#22c55e" : "#ef4444") + ';">' + (q.net_profit == null ? "\u2014" : "\u20B9" + q.net_profit.toLocaleString("en-IN", { maximumFractionDigits: 2 }) + " Cr") + '</span></div>';
    });

    return '<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:1.25rem;">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.5rem;">'
        + '<h3 style="font-size:1.1rem;font-weight:700;margin:0;">Fundamental Analysis</h3>'
        + '<span style="font-size:0.7rem;color:var(--text-muted);">Source: screener.in \u00b7 ' + escapeHtml(f.updated_at || "") + '</span>'
        + '</div>'
        + '<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.75rem;flex-wrap:wrap;">'
        + (h.name ? '<span style="font-size:0.9rem;font-weight:600;">' + escapeHtml(h.name) + '</span>' : '')
        + (h.sector ? '<span style="font-size:0.72rem;color:var(--text-secondary);background:var(--bg-primary);padding:0.2rem 0.55rem;border-radius:12px;">' + escapeHtml(h.sector) + '</span>' : '')
        + '</div>'
        + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:0.45rem;margin-bottom:1rem;">'
        + revChip + revYoY + revCagr + npChip + npYoY + npTtm + opmChip + nmChip + peChip + mcapChip + roeChip + roceChip + debtChip + promChip + cccChip + cfoChip
        + '</div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem;">'
        + '<div style="padding:0.75rem;background:rgba(34,197,94,0.05);border:1px solid rgba(34,197,94,0.15);border-radius:8px;">'
        + '<div style="font-size:0.7rem;font-weight:700;color:#22c55e;text-transform:uppercase;margin-bottom:0.35rem;">The Good</div>' + goodHtml + '</div>'
        + '<div style="padding:0.75rem;background:rgba(239,68,68,0.05);border:1px solid rgba(239,68,68,0.15);border-radius:8px;">'
        + '<div style="font-size:0.7rem;font-weight:700;color:#ef4444;text-transform:uppercase;margin-bottom:0.35rem;">The Problems</div>' + problemHtml + '</div>'
        + '</div>'
        + '<div style="padding:0.6rem 0.75rem;background:var(--bg-primary);border-left:2px solid #f59e0b;border-radius:6px;margin-bottom:1rem;font-size:0.85rem;">'
        + '<div style="font-size:0.7rem;font-weight:700;color:#f59e0b;text-transform:uppercase;margin-bottom:0.25rem;">Earnings Quality</div>' + qualityHtml + '</div>'
        + '<div style="display:flex;gap:0.75rem;align-items:flex-start;margin-bottom:1rem;">'
        + '<div style="flex:1;padding:0.75rem;background:rgba(59,130,246,0.07);border:1px solid rgba(59,130,246,0.2);border-radius:8px;">'
        + '<div style="font-size:0.7rem;font-weight:700;color:#3b82f6;text-transform:uppercase;margin-bottom:0.3rem;">Verdict</div>'
        + '<div style="font-size:0.85rem;line-height:1.5;">' + escapeHtml(f.verdict || "") + '</div>'
        + '<div style="font-size:0.8rem;color:var(--text-secondary);margin-top:0.5rem;"><b>Watch:</b> ' + escapeHtml(f.watch || "") + '</div>'
        + '</div>'
        + '<div style="min-width:110px;text-align:center;padding:0.75rem;background:' + riskBg + ';border:1px solid ' + riskColor + ';border-radius:8px;">'
        + '<div style="font-size:0.62rem;color:var(--text-muted);text-transform:uppercase;">Risk Level</div>'
        + '<div style="font-size:1.1rem;font-weight:800;color:' + riskColor + ';">' + escapeHtml(f.risk_level || "\u2014") + '</div></div>'
        + '</div>'
        + '<div style="padding:0.6rem 0.75rem;background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.2);border-left:2px solid #f59e0b;border-radius:6px;font-size:0.75rem;color:#fbbf24;margin-bottom:1rem;">'
        + '&#9888; ' + escapeHtml(f.disclaimer || "") + '</div>'
        + '<div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);text-transform:uppercase;margin-bottom:0.35rem;">Recent Quarterly Results (Sales \/ Net Profit)</div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.4rem;padding:0.35rem 0;border-bottom:1px solid var(--border-color);font-size:0.75rem;color:var(--text-muted);font-weight:600;">'
        + '<span>Quarter</span><span>Sales</span><span>Net Profit</span></div>' + quarterRows
        + '</div>';
}

function signalPlanHTML(sig) {
    if (!sig) return "";
    var isBuy = sig.action === "BUY";
    var accent = isBuy ? "#16a34a" : "#dc2626";
    var headerBg = isBuy ? "rgba(22,163,74,0.12)" : "rgba(220,38,38,0.12)";
    var rows = '';
    rows += '<div class="detail-item"><span class="detail-label">Signal</span><span class="detail-value"><b>' + escapeHtml(sig.segment) + '</b> \u2014 ' + escapeHtml(sig.action) + ' \u00b7 ' + escapeHtml(sig.direction) + '</span></div>';
    if (sig.entry_price != null) rows += '<div class="detail-item"><span class="detail-label">Entry</span><span class="detail-value">' + formatPrice(sig.entry_price) + '</span></div>';
    if (sig.target_1 != null) rows += '<div class="detail-item"><span class="detail-label">Target 1</span><span class="detail-value" style="color:#22c55e;">' + formatPrice(sig.target_1) + '</span></div>';
    if (sig.target_2 != null) rows += '<div class="detail-item"><span class="detail-label">Target 2</span><span class="detail-value" style="color:#22c55e;">' + formatPrice(sig.target_2) + '</span></div>';
    if (sig.stop_loss != null) rows += '<div class="detail-item"><span class="detail-label">Stop Loss</span><span class="detail-value" style="color:#ef4444;">' + formatPrice(sig.stop_loss) + '</span></div>';
    if (sig.rr_ratio != null) rows += '<div class="detail-item"><span class="detail-label">R:R</span><span class="detail-value">' + sig.rr_ratio + '</span></div>';
    rows += '<div class="detail-item"><span class="detail-label">Confidence</span><span class="detail-value">' + (sig.confidence || "\u2014") + '%</span></div>';
    var note = sig.chart_note ? '<div style="margin-top:8px;font-size:11px;color:#94a3b8;padding:6px 10px;background:rgba(10,14,23,0.7);border-radius:6px;border-left:2px solid ' + accent + ';">' + escapeHtml(sig.chart_note) + '</div>' : "";
    var disclaim = sig.disclaimer ? '<div style="margin-top:6px;font-size:11px;color:#fbbf24;padding:6px 10px;background:rgba(28,21,5,0.8);border-radius:6px;border-left:2px solid #f59e0b;">&#9888; ' + escapeHtml(sig.disclaimer) + '</div>' : "";
    return '<div style="background:var(--bg-card);border:1px solid ' + accent + ';border-radius:10px;padding:1.1rem 1.25rem;margin-bottom:1rem;' + ('background:' + headerBg) + ';">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
        + '<div style="font-size:0.75rem;font-weight:700;color:' + accent + ';letter-spacing:0.03em;text-transform:uppercase;">Live Signal Plan \u2014 ' + escapeHtml(sig.strategy_name) + '</div>'
        + '<span style="font-size:0.7rem;color:' + accent + ';">' + escapeHtml(sig.entry_timestamp || "") + '</span>'
        + '</div>'
        + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:0.4rem;">' + rows + '</div>'
        + note + disclaim
        + '</div>';
}

function initChartSignals() {
    var sel = document.getElementById("chart-signal-sel");
    if (!sel) return;
    sel.addEventListener("change", function () {
        if (sel.value) {
            var input = document.getElementById("chart-ticker");
            if (input) input.value = sel.value;
            loadChartAnalysis(sel.value);
        }
    });
    fetchAPI("/api/signals", 60000).then(function (result) {
        var sigs = (result.signals || []).filter(function (s) { return !!(s.ticker); });
        var opts = '<option value="">\u2014 Select a live signal \u2014</option>';
        sigs.forEach(function (s) {
            opts += '<option value="' + s.ticker + '">' + s.ticker + ' \u00b7 ' + s.segment + ' \u00b7 ' + s.action + ' \u00b7 conf ' + (s.confidence || "") + '</option>';
        });
        sel.innerHTML = opts;
        var hasTicker = !!document.getElementById("chart-ticker").value;
        if (!hasTicker && sigs.length && !(new URLSearchParams(window.location.search).get("ticker"))) {
            sel.value = sigs[0].ticker;
            document.getElementById("chart-ticker").value = sigs[0].ticker;
            loadChartAnalysis(sigs[0].ticker);
        }
    }).catch(function () {});
}

function initChartScanner() {
    var input = document.getElementById("chart-ticker");
    var btn = document.getElementById("chart-go");
    if (!input || !btn) return;
    function go() {
        var v = input.value.trim();
        if (v) loadChartAnalysis(v.toUpperCase());
    }
    btn.onclick = go;
    input.onkeydown = function (e) { if (e.key === "Enter") go(); };
    var urlTicker = new URLSearchParams(window.location.search).get("ticker");
    if (urlTicker) {
        input.value = urlTicker.toUpperCase();
        loadChartAnalysis(urlTicker.toUpperCase());
    }
}

/* ─────── Bookmark helpers ─────── */
function getBookmarks() {
    try { return JSON.parse(localStorage.getItem("news_bookmarks") || "[]"); }
    catch (e) { return []; }
}

function saveBookmarks(ids) {
    localStorage.setItem("news_bookmarks", JSON.stringify(ids));
}

function toggleBookmark(id) {
    var b = getBookmarks();
    var idx = b.indexOf(id);
    if (idx === -1) { b.push(id); } else { b.splice(idx, 1); }
    saveBookmarks(b);
    return b;
}

function isBookmarked(id) {
    return getBookmarks().indexOf(id) !== -1;
}

/* ─────── News with Impact (news page + embedded) ─────── */
var _newsData = [];
var _showBookmarksOnly = false;

function renderNewsInsight(item) {
    var sentimentMap = { positive: "\uD83D\uDFE2 Positive", negative: "\uD83D\uDD34 Negative", neutral: "\u26AA Neutral" };
    var bookmarked = isBookmarked(item.id);
    var bookmarkBtn = '<button class="news-bookmark-btn" data-id="' + item.id + '" style="background:none;border:none;cursor:pointer;font-size:1.1rem;padding:2px 6px;border-radius:4px;transition:all 0.15s;' + (bookmarked ? 'color:#eab308;' : 'color:#64748b;') + '" title="' + (bookmarked ? 'Remove bookmark' : 'Bookmark this news') + '">'
        + (bookmarked ? '\u2B50' : '\u2606')
        + '</button>';
    var dateStr = "";
    if (item.published_at) {
        var d = new Date(item.published_at.replace(" ", "T"));
        var today = new Date();
        var diffDays = Math.floor((today - d) / (1000 * 60 * 60 * 24));
        if (diffDays === 0) dateStr = "Today";
        else if (diffDays === 1) dateStr = "Yesterday";
        else dateStr = diffDays + " days ago";
    }
    var stocksHtml = "";
    if (item.affected_stocks && item.affected_stocks.length) {
        var links = [];
        for (var i = 0; i < item.affected_stocks.length; i++) {
            var s = item.affected_stocks[i];
            links.push('<a href="#" class="news-stock-link" data-ticker="' + s + '" style="color:#3b82f6;text-decoration:underline;cursor:pointer;">' + s + '</a>');
        }
        stocksHtml = '<div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.375rem;"><strong>Affected:</strong> ' + links.join(", ") + '</div>';
    }
    var predictionHtml = item.prediction ? '<div style="font-size:0.8rem;margin-bottom:0.3rem;"><span style="color:#3b82f6;font-weight:600;">\uD83D\uDD2E Prediction:</span> ' + item.prediction + '</div>' : "";
    var cautionHtml = item.caution ? '<div style="font-size:0.8rem;margin-bottom:0.3rem;"><span style="color:#eab308;font-weight:600;">\u26A0\uFE0F Caution:</span> ' + item.caution + '</div>' : "";
    var dosHtml = item.dos && item.dos.length ? '<div style="font-size:0.8rem;color:#22c55e;margin-bottom:0.2rem;"><strong>\u2705 Do\'s:</strong> ' + item.dos.join(" \u00B7 ") + '</div>' : "";
    var dontsHtml = item.donts && item.donts.length ? '<div style="font-size:0.8rem;color:#ef4444;"><strong>\u274C Don\'ts:</strong> ' + item.donts.join(" \u00B7 ") + '</div>' : "";
    return '<div class="news-item ' + (bookmarked ? 'bookmarked' : '') + '" style="margin-bottom:0.75rem;">'
        + '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem;">'
        + '<div style="flex:1;">'
        + '<a href="' + item.url + '" target="_blank" rel="noopener" class="news-title">' + item.title + '</a>'
        + (item.summary ? '<p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.375rem;">' + item.summary + '</p>' : "")
        + '<div class="news-meta" style="margin-bottom:0.5rem;">'
        + '<span>' + (item.source || "") + '</span>'
        + '<span>' + (dateStr || item.published_at || "") + '</span>'
        + '<span>' + (sentimentMap[item.sentiment] || "") + '</span>'
        + (item.sector ? '<span style="padding:0.1rem 0.4rem;background:var(--bg-hover);border-radius:4px;font-size:0.7rem;">' + item.sector + '</span>' : "")
        + '</div>'
        + stocksHtml
        + predictionHtml
        + cautionHtml
        + dosHtml
        + dontsHtml
        + '</div>'
        + bookmarkBtn
        + '</div>'
        + '</div>';
}

function renderNewsList() {
    var container = document.getElementById("news-container");
    if (!container) return;
    var filtered = _newsData;
    if (_showBookmarksOnly) {
        var b = getBookmarks();
        filtered = _newsData.filter(function (item) { return b.indexOf(item.id) !== -1; });
    }
    if (!filtered.length) {
        container.innerHTML = '<div class="empty-state"><h3>' + (_showBookmarksOnly ? 'No Bookmarked News' : 'No News Available') + '</h3><p>' + (_showBookmarksOnly ? 'Click the star icon on news items to bookmark them.' : '') + '</p></div>';
        return;
    }
    container.innerHTML = filtered.map(renderNewsInsight).join("");
    var countEl = document.getElementById("news-count");
    if (countEl) countEl.textContent = filtered.length;
}

async function loadNews() {
    var container = document.getElementById("news-container");
    if (!container) return;
    try {
        var data = await fetchAPI("/api/news?limit=20");
        if (!data.news || data.news.length === 0) {
            container.innerHTML = '<div class="empty-state"><h3>No News Available</h3></div>';
            return;
        }
        _newsData = data.news;
        renderNewsList();
    } catch (err) {
        container.innerHTML = '<div class="empty-state"><h3>Error Loading News</h3><p>' + err.message + '</p></div>';
    }
}

function toggleBookmarkFilter() {
    _showBookmarksOnly = !_showBookmarksOnly;
    var btn = document.getElementById("bookmark-filter-btn");
    if (btn) {
        btn.textContent = _showBookmarksOnly ? "\u2B50 Show All News" : "\u2606 Show Bookmarks Only";
        btn.className = _showBookmarksOnly ? "btn btn-primary" : "btn";
    }
    renderNewsList();
}

function initNewsClickDelegation() {
    document.addEventListener("click", function (e) {
        var target = e.target;
        while (target && target !== document) {
            if (target.classList && target.classList.contains("news-stock-link")) {
                e.preventDefault();
                var ticker = target.getAttribute("data-ticker");
                if (ticker) loadChartAnalysis(ticker);
                return;
            }
            if (target.classList && target.classList.contains("news-bookmark-btn")) {
                var id = target.getAttribute("data-id");
                if (id) {
                    toggleBookmark(id);
                    renderNewsList();
                }
                return;
            }
            target = target.parentNode;
        }
    });
    var filterBtn = document.getElementById("bookmark-filter-btn");
    if (filterBtn) filterBtn.onclick = toggleBookmarkFilter;
}

/* ─────── Position Size Calculator (dashboard) ─────── */
function initCalculator() {
    var entryEl = document.getElementById("entry-price");
    var stopEl = document.getElementById("stop-loss");
    var capitalEl = document.getElementById("total-capital");
    var riskEl = document.getElementById("risk-pct");
    var resultEl = document.getElementById("calc-shares");
    if (!entryEl || !stopEl || !capitalEl || !riskEl || !resultEl) return;
    function calculate() {
        var entry = parseFloat(entryEl.value);
        var stop = parseFloat(stopEl.value);
        var capital = parseFloat(capitalEl.value);
        var riskPct = parseFloat(riskEl.value);
        var riskAmt = capital * (riskPct / 100);
        var perShareRisk = Math.abs(entry - stop);
        if (!entry || !stop || !capital || !riskPct || perShareRisk === 0) {
            resultEl.textContent = "\u2014";
            return;
        }
        var shares = Math.floor(riskAmt / perShareRisk);
        resultEl.textContent = isNaN(shares) ? "\u2014" : shares.toLocaleString("en-IN");
    }
    entryEl.oninput = calculate;
    stopEl.oninput = calculate;
    capitalEl.oninput = calculate;
    riskEl.oninput = calculate;
    calculate();
}

/* ─────── Tabs (dashboard) ─────── */
function initTabs() {
    var tabs = document.querySelectorAll(".tab");
    if (!tabs.length) return;
    tabs.forEach(function (tab) {
        tab.onclick = function () {
            tabs.forEach(function (t) { t.classList.remove("active"); });
            this.classList.add("active");
            currentFilter = { segment: this.getAttribute("data-segment") || null, direction: null };
            loadSignals();
        };
    });
}

/* ─────── Trade Journal (journal page) ─────── */
function getTrades() {
    try { return JSON.parse(localStorage.getItem("journal_trades") || "[]"); }
    catch (e) { return []; }
}
function saveTrades(t) { localStorage.setItem("journal_trades", JSON.stringify(t)); }

function calcPnL(trade) {
    var qty = parseInt(trade.qty) || 1;
    var entry = parseFloat(trade.entry);
    var exit = parseFloat(trade.exit);
    if (!entry || !exit) return 0;
    return trade.direction === "BUY" ? (exit - entry) * qty : (entry - exit) * qty;
}

function renderJournal() {
    var trades = getTrades();
    var total = trades.length;
    var wins = trades.filter(function (t) { return t.result === "WIN"; }).length;
    var losses = trades.filter(function (t) { return t.result === "LOSS"; }).length;
    var winrate = total ? ((wins / total) * 100).toFixed(1) : 0;
    var pnl = trades.reduce(function (s, t) { return s + calcPnL(t); }, 0);
    var rrSum = trades.reduce(function (s, t) { return s + (parseFloat(t.rr) || 0); }, 0);
    var avgRR = total ? (rrSum / total).toFixed(2) : "0";

    var totalEl = document.getElementById("j-total");
    var winsEl = document.getElementById("j-wins");
    var lossesEl = document.getElementById("j-losses");
    var wrEl = document.getElementById("j-winrate");
    var pnlEl = document.getElementById("j-pnl");
    var rrEl = document.getElementById("j-avgrr");
    if (totalEl) totalEl.textContent = total;
    if (winsEl) winsEl.textContent = wins;
    if (lossesEl) lossesEl.textContent = losses;
    if (wrEl) { wrEl.textContent = winrate + "%"; wrEl.style.color = winrate >= 50 ? "#22c55e" : "#ef4444"; }
    if (pnlEl) { pnlEl.textContent = "\u20B9" + pnl.toLocaleString("en-IN"); pnlEl.style.color = pnl >= 0 ? "#22c55e" : "#ef4444"; }
    if (rrEl) rrEl.textContent = avgRR;

    var container = document.getElementById("journal-trades");
    if (!container) return;
    if (!trades.length) {
        container.innerHTML = '<div class="empty-journal"><h3>No Trades Logged</h3><p>Start by adding your first trade above.</p></div>';
        return;
    }
    var html = '<h3 style="font-size:0.9rem;font-weight:600;margin-bottom:0.5rem;">Trade History (' + total + ')</h3>';
    for (var i = trades.length - 1; i >= 0; i--) {
        var t = trades[i];
        var p = calcPnL(t);
        var pnlCls = p >= 0 ? "positive" : "negative";
        var pnlSign = p >= 0 ? "+" : "";
        html += '<div class="trade-row">'
            + '<div class="info"><strong>' + t.ticker + '</strong> ' + t.direction
            + ' <span style="color:var(--text-muted);font-size:0.75rem;">| ' + t.date + '</span>'
            + '<div class="meta">Entry: \u20B9' + parseFloat(t.entry).toFixed(2) + ' | Exit: \u20B9' + parseFloat(t.exit).toFixed(2) + ' | Qty: ' + t.qty
            + (t.rr ? ' | R: ' + t.rr : '')
            + (t.result === "WIN" ? ' | <span style="color:#22c55e;">WIN</span>' : ' | <span style="color:#ef4444;">LOSS</span>')
            + (t.notes ? '<br>' + t.notes : '')
            + '</div></div>'
            + '<div class="pnl ' + pnlCls + '">' + pnlSign + '\u20B9' + Math.abs(p).toLocaleString("en-IN") + '</div>'
            + '</div>';
    }
    container.innerHTML = html;
}

function addTrade() {
    var date = document.getElementById("trade-date");
    var ticker = document.getElementById("trade-ticker");
    var direction = document.getElementById("trade-direction");
    var qty = document.getElementById("trade-qty");
    var entry = document.getElementById("trade-entry");
    var exit = document.getElementById("trade-exit");
    var result = document.getElementById("trade-result");
    var rr = document.getElementById("trade-rr");
    var notes = document.getElementById("trade-notes");
    if (!date || !ticker || !entry || !exit) return;
    if (!ticker.value.trim()) { alert("Enter a ticker symbol."); ticker.focus(); return; }
    if (!entry.value || !exit.value) { alert("Enter entry and exit prices."); return; }
    var trades = getTrades();
    trades.push({
        date: date.value || (function(){ var d=new Date(); return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); })(),
        ticker: ticker.value.trim().toUpperCase(),
        direction: direction.value,
        qty: parseInt(qty.value) || 1,
        entry: parseFloat(entry.value),
        exit: parseFloat(exit.value),
        result: result.value,
        rr: parseFloat(rr.value) || 0,
        notes: notes.value.trim(),
        added: new Date().toISOString(),
    });
    saveTrades(trades);
    ticker.value = ""; entry.value = ""; exit.value = ""; rr.value = ""; notes.value = "";
    renderJournal();
}

function clearJournal() {
    if (!confirm("Delete all trade records?")) return;
    saveTrades([]);
    renderJournal();
}

function initJournal() {
    var dateEl = document.getElementById("trade-date");
    if (dateEl && !dateEl.value) { var d=new Date(); dateEl.value = d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); }
    renderJournal();
}

function formatIndexValue(val) {
    if (val == null || isNaN(val)) return "\u2014";
    return Number(val).toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function formatNum(val, decimals) {
    if (val == null || isNaN(val)) return "\u2014";
    return (val >= 0 ? "+" : "") + Number(val).toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/* ─────── Sector Rotation (sectors page) ─────── */
async function loadSectors() {
    var grid = document.getElementById("sector-grid");
    var rankContainer = document.getElementById("sector-rank-container");
    var tsEl = document.getElementById("sector-timestamp");
    if (!grid) return;
    try {
        var data = await fetchAPI("/api/sectors");
        grid.innerHTML = data.sectors.map(function (s) {
            var cls = s.trend === "bullish" ? "positive" : s.trend === "bearish" ? "negative" : "";
            var badge = '<span class="badge badge-' + s.trend + '">' + s.trend.toUpperCase() + '</span>';
            var chgLine = '<span style="font-size:0.9rem;">' + formatNum(s.change, 2) + ' | ' + formatNum(s.change_pct, 2) + '%</span>';
            return '<div class="sector-card"><div class="sector-name">' + s.name + ' ' + badge + '</div>'
                + '<div class="sector-change ' + cls + '"><span style="font-size:1.05rem;">' + formatIndexValue(s.last) + '</span> ' + chgLine + '</div>'
                + (s.top_stock ? '<div class="sector-top">Top: ' + s.top_stock + '</div>' : '') + '</div>';
        }).join("");
        if (rankContainer) {
            rankContainer.innerHTML = '<div style="display:flex;gap:1rem;flex-wrap:wrap;">'
                + '<span style="font-size:0.85rem;"><strong>&#x1F7E2; Top:</strong> ' + data.top_sector + '</span>'
                + '<span style="font-size:0.85rem;"><strong>&#x1F534; Bottom:</strong> ' + data.bottom_sector + '</span>'
                + '<span style="font-size:0.85rem;color:var(--text-muted);"><strong>Strategy:</strong> Rotate into leading sectors, avoid laggards.</span>'
                + '</div>';
        }
        if (tsEl) tsEl.textContent = "Updated: " + (data.timestamp || "");
    } catch (err) {
        grid.innerHTML = '<div class="empty-state"><h3>Error</h3><p>' + err.message + '</p></div>';
    }
}

/* ─────── FII/DII Flows (flows page) ─────── */
async function loadFlows() {
    var summaryEl = document.getElementById("flow-summary");
    var tableEl = document.getElementById("flow-table");
    var tsEl = document.getElementById("flow-timestamp");
    if (!summaryEl) return;
    try {
        var data = await fetchAPI("/api/flows");
        if (data.available === false || !data.summary) {
            tableEl.innerHTML = '<div class="empty-state"><h3>FII/DII Data Unavailable</h3><p>' + (data.disclaimer || "Live source not reachable right now.") + '</p></div>';
            return;
        }
        var s = data.summary;
        summaryEl.innerHTML = '<div class="flow-stat"><div class="num" style="color:' + (s.fii_trend === "bullish" ? "#22c55e" : "#ef4444") + ';">' + (s.total_fii_crore >= 0 ? "+" : "") + s.total_fii_crore.toLocaleString("en-IN") + '</div><div class="lbl">FII (Cr) - 30D</div></div>'
            + '<div class="flow-stat"><div class="num" style="color:#3b82f6;">' + (s.total_dii_crore >= 0 ? "+" : "") + s.total_dii_crore.toLocaleString("en-IN") + '</div><div class="lbl">DII (Cr) - 30D</div></div>'
            + '<div class="flow-stat"><div class="num" style="color:' + (s.net_crore >= 0 ? "#22c55e" : "#ef4444") + ';">' + (s.net_crore >= 0 ? "+" : "") + s.net_crore.toLocaleString("en-IN") + '</div><div class="lbl">Net (Cr) - 30D</div></div>'
            + '<div class="flow-stat"><div class="num" style="color:' + (s.fii_trend === "bullish" ? "#22c55e" : "#ef4444") + ';">' + s.fii_trend.toUpperCase() + '</div><div class="lbl">FII Trend</div></div>';
        var html = "";
        for (var i = 0; i < data.daily.length; i++) {
            var d = data.daily[i];
            var maxVal = Math.max(Math.abs(d.fii_crore), 1);
            var fiiPct = Math.min(Math.abs(d.fii_crore) / 4500 * 100, 100);
            var diiPct = Math.min(Math.abs(d.dii_crore) / 3000 * 100, 100);
            var fiiColor = d.fii_crore >= 0 ? "#22c55e" : "#ef4444";
            var diiColor = d.dii_crore >= 0 ? "#3b82f6" : "#ef4444";
            html += '<div class="flow-bar"><span class="flow-date">' + d.date + '</span>'
                + '<span class="flow-label">FII</span><div class="bar-track"><div class="bar-fill" style="width:' + fiiPct + '%;background:' + fiiColor + ';"></div></div>'
                + '<span style="font-size:0.75rem;font-weight:600;min-width:65px;text-align:right;color:' + fiiColor + ';">' + (d.fii_crore >= 0 ? "+" : "") + d.fii_crore + '</span>'
                + '</div>';
            html += '<div class="flow-bar"><span class="flow-date"></span>'
                + '<span class="flow-label">DII</span><div class="bar-track"><div class="bar-fill" style="width:' + diiPct + '%;background:' + diiColor + ';"></div></div>'
                + '<span style="font-size:0.75rem;font-weight:600;min-width:65px;text-align:right;color:' + diiColor + ';">' + (d.dii_crore >= 0 ? "+" : "") + d.dii_crore + '</span>'
                + '</div>';
        }
        tableEl.innerHTML = html;
        if (tsEl) tsEl.textContent = "Updated: " + (data.timestamp || "");
    } catch (err) {
        tableEl.innerHTML = '<div class="empty-state"><h3>Error</h3><p>' + err.message + '</p></div>';
    }
}

/* ─────── Market Breadth (breadth page) ─────── */
async function loadBreadth() {
    var gridEl = document.getElementById("breadth-grid");
    var statusEl = document.getElementById("breadth-status");
    var barEl = document.getElementById("breadth-bar");
    var insightEl = document.getElementById("breadth-insight");
    var tsEl = document.getElementById("breadth-timestamp");
    if (!gridEl) return;
    try {
        var data = await fetchAPI("/api/breadth");
        if (data.available === false || data.total == null) {
            gridEl.innerHTML = '<div class="empty-state"><h3>Market Breadth Unavailable</h3><p>' + (data.disclaimer || "Could not collect enough live quotes to compute breadth.") + '</p></div>';
            return;
        }
        var upPct = data.total ? (data.advances / data.total * 100).toFixed(1) : 0;
        var downPct = data.total ? (data.declines / data.total * 100).toFixed(1) : 0;
        var uncPct = data.total ? (data.unchanged / data.total * 100).toFixed(1) : 0;
        var statusClass = "status-" + data.breadth_status;
        var statusLabel = data.breadth_status === "strong" ? "Strong Breadth \u2014 Bullish" : data.breadth_status === "weak" ? "Weak Breadth \u2014 Bearish" : "Mixed Breadth \u2014 Neutral";
        gridEl.innerHTML = '<div class="breadth-card"><div class="num" style="color:#22c55e;">' + data.advances + '</div><div class="lbl">Advances</div></div>'
            + '<div class="breadth-card"><div class="num" style="color:#ef4444;">' + data.declines + '</div><div class="lbl">Declines</div></div>'
            + '<div class="breadth-card"><div class="num" style="color:#64748b;">' + data.unchanged + '</div><div class="lbl">Unchanged</div></div>'
            + '            <div class="breadth-card"><div class="num" style="color:' + (data.advance_decline_ratio >= 1.0 ? "#22c55e" : "#ef4444") + ';">' + data.advance_decline_ratio + '</div><div class="lbl">Adv/Dec Ratio</div></div>'
            + '<div class="breadth-card"><div class="num" style="color:#22c55e;">' + data.week52_high + '</div><div class="lbl">3-Mo Highs</div></div>'
            + '<div class="breadth-card"><div class="num" style="color:#ef4444;">' + data.week52_low + '</div><div class="lbl">3-Mo Lows</div></div>';
        if (statusEl) statusEl.innerHTML = '<div class="breadth-status ' + statusClass + '">' + statusLabel + '</div>';
        if (barEl) barEl.innerHTML = '<div class="segment adv" style="width:' + upPct + '%;">' + (upPct > 10 ? data.advances : "") + '</div>'
            + '<div class="segment dec" style="width:' + downPct + '%;">' + (downPct > 10 ? data.declines : "") + '</div>'
            + '<div class="segment unc" style="width:' + uncPct + '%;"></div>';
        if (insightEl) {
            var insight = (data.breadth_status === "strong"
                ? "\uD83D\uDFE2 <strong>Bullish</strong> \u2014 More than 1.5x stocks advancing than declining within the scanned universe."
                : data.breadth_status === "weak"
                ? "\uD83D\uDD34 <strong>Bearish</strong> \u2014 More than 1.5x stocks declining than advancing within the scanned universe."
                : "\uD83D\uDFE1 <strong>Mixed</strong> \u2014 No clear direction. Advances and declines are balanced.")
                + '<br><span style="font-size:0.7rem;color:var(--text-muted);">Scope: ' + (data.scope || "NIFTY-200") + '. ' + (data.highlow_note || "Highs/Lows are relative to the trailing 3-month window.") + '</span>';
            insightEl.innerHTML = '<div class="breadth-insight">' + insight + '</div>';
        }
        if (tsEl) tsEl.textContent = "Updated: " + (data.timestamp || "");
    } catch (err) {
        gridEl.innerHTML = '<div class="empty-state"><h3>Error</h3><p>' + err.message + '</p></div>';
    }
}

/* ─────── Dropdown ─────── */
function initDropdown() {
    document.addEventListener("click", function (e) {
        var toggle = e.target.closest(".dropdown-toggle");
        if (toggle) {
            e.preventDefault();
            var dd = toggle.parentElement;
            if (dd) dd.classList.toggle("open");
            return;
        }
        var open = document.querySelectorAll(".nav-dropdown.open");
        for (var i = 0; i < open.length; i++) {
            if (!open[i].contains(e.target)) open[i].classList.remove("open");
        }
    });
}

/* ─────── Stocks / Screener ─────── */
var stockState = { universe: "500", q: "", sortBy: "change_pct", order: "desc" };

function initStocks() {
    var tabs = document.querySelectorAll("[data-universe]");
    tabs.forEach(function (t) {
        t.addEventListener("click", function () {
            stockState.universe = t.getAttribute("data-universe");
            tabs.forEach(function (x) { x.classList.remove("active"); });
            t.classList.add("active");
            loadStocks();
        });
    });
    var search = document.getElementById("stock-search");
    if (search) {
        var debounce;
        search.addEventListener("input", function () {
            clearTimeout(debounce);
            debounce = setTimeout(function () {
                stockState.q = search.value.trim();
                loadStocks();
            }, 250);
        });
    }
    var signalFilter = document.getElementById("stock-signal-filter");
    if (signalFilter) signalFilter.addEventListener("change", function () { loadStocks(); });
    loadStocks();
}

function stockSortBy(key) {
    if (stockState.sortBy === key) {
        stockState.order = stockState.order === "asc" ? "desc" : "asc";
    } else {
        stockState.sortBy = key;
        stockState.order = key === "ticker" || key === "name" ? "asc" : "desc";
    }
    loadStocks();
}

function openChartTicker(ticker) {
    if (ticker) window.location.href = "/chart?ticker=" + ticker;
}

async function loadStocks() {
    var tbody = document.getElementById("stocks-tbody");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6"><div class="loading"><div class="spinner"></div><p>Loading stocks...</p></div></td></tr>';
    var filterEl = document.getElementById("stock-signal-filter");
    var signal = filterEl ? filterEl.value : "any";
    var url = "/api/stocks?universe=" + stockState.universe
        + "&sort_by=" + stockState.sortBy + "&order=" + stockState.order
        + "&signal=" + signal;
    if (stockState.q) url += "&q=" + encodeURIComponent(stockState.q);
    try {
        var result = await fetchAPI(url, 30000);
        var rows = result.stocks || [];
        var hh = document.getElementById("stocks-count");
        if (hh) hh.textContent = rows.length;
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text-muted);">No stocks found.</td></tr>';
            return;
        }
        var html = "";
        rows.forEach(function (s) {
            var dir = s.change_pct == null ? "" : (s.change_pct >= 0 ? "positive" : "negative");
            var pct = s.change_pct == null ? "\u2014" : (s.change_pct >= 0 ? "+" : "") + s.change_pct.toFixed(2) + "%";
            var sigBadge = s.signal ? '<span class="signal-badge ' + s.signal.toLowerCase().replace(" ", "-") + '">' + s.signal + '</span>' : "";
            html += '<tr style="cursor:pointer;" onclick="openChartTicker(\'' + s.ticker + '\')">'
                + '<td><b>' + escapeHtml(s.ticker) + '</b><div style="font-size:0.7rem;color:var(--text-muted);">' + escapeHtml(s.name || "") + '</div></td>'
                + '<td>' + formatPrice(s.last) + '</td>'
                + '<td class="' + dir + '">' + pct + '</td>'
                + '<td>' + (s.volume != null ? Number(s.volume).toLocaleString("en-IN") : "\u2014") + '</td>'
                + '<td>' + (sigBadge || "") + '</td>'
                + '<td style="color:#3b82f6;">Analyze \u2192</td>'
                + '</tr>';
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--accent-red);">Failed to load: ' + escapeHtml(e.message) + '</td></tr>';
    }
}

/* ─────── Portfolio ─────── */
function initPortfolio() {
    var form = document.getElementById("portfolio-form");
    if (form) {
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            addPosition();
        });
    }
    loadPortfolio();
}

async function loadPortfolio() {
    var table = document.getElementById("portfolio-tbody");
    var summaryBox = document.getElementById("portfolio-summary");
    if (!table) return;
    try {
        var data = await fetchAPI("/api/portfolio", 20000);
        var sum = data.summary || {};
        if (summaryBox) {
            var pnlColor = (sum.total_pnl || 0) >= 0 ? "var(--accent-green)" : "var(--accent-red)";
            summaryBox.innerHTML = ''
                + '<div class="journal-stat"><div class="num">' + (sum.positions_count || 0) + '</div><div class="lbl">Holdings</div></div>'
                + '<div class="journal-stat"><div class="num">' + formatPrice(sum.total_invested) + '</div><div class="lbl">Invested</div></div>'
                + '<div class="journal-stat"><div class="num">' + formatPrice(sum.total_value) + '</div><div class="lbl">Current Value</div></div>'
                + '<div class="journal-stat"><div class="num" style="color:' + pnlColor + ';">' + ((sum.total_pnl || 0) >= 0 ? "+" : "") + formatPrice(sum.total_pnl) + '</div><div class="lbl">Total P&amp;L</div></div>'
                + '<div class="journal-stat"><div class="num" style="color:' + pnlColor + ';">' + (sum.total_pnl_pct != null ? (sum.total_pnl_pct >= 0 ? "+" : "") + sum.total_pnl_pct.toFixed(2) + "%" : "\u2014") + '</div><div class="lbl">P&amp;L %</div></div>';
        }
        var rows = data.positions || [];
        if (!rows.length) {
            table.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text-muted);">No holdings yet. Add a position below or click "+ Add" on a live signal.</td></tr>';
            return;
        }
        var html = "";
        rows.forEach(function (p) {
            var pnlC = p.pnl == null ? "--" : (p.pnl >= 0 ? "+" : "") + formatPrice(p.pnl);
            var pnlCls = p.pnl == null ? "" : (p.pnl >= 0 ? "positive" : "negative");
            var pnlPct = p.pnl_pct == null ? "\u2014" : (p.pnl_pct >= 0 ? "+" : "") + p.pnl_pct.toFixed(2) + "%";
            var segBadge = '<span class="signal-badge ' + p.segment.toLowerCase().replace(" ", "-") + '">' + p.segment + '</span>';
            html += '<tr>'
                + '<td><b style="cursor:pointer;color:#3b82f6;" onclick="openChartTicker(\'' + p.ticker + '\')">' + escapeHtml(p.ticker) + '</b> ' + segBadge + '</td>'
                + '<td>' + p.qty + '</td>'
                + '<td>' + formatPrice(p.avg_price) + '</td>'
                + '<td>' + formatPrice(p.last_price) + '</td>'
                + '<td>' + formatPrice(p.invested) + '</td>'
                + '<td>' + formatPrice(p.current_value) + '</td>'
                + '<td class="' + pnlCls + '">' + pnlC + ' (' + pnlPct + ')</td>'
                + '<td><button class="btn btn-sm" onclick="editPosition(\'' + p.id + '\')">Edit</button> '
                + '<button class="btn btn-sm btn-danger" onclick="deletePosition(\'' + p.id + '\')">\u2715</button></td>'
                + '</tr>';
        });
        table.innerHTML = html;
    } catch (e) {
        if (summaryBox) summaryBox.innerHTML = '<div class="journal-stat" style="grid-column:1/-1;color:var(--accent-red);">Failed to load portfolio: ' + escapeHtml(e.message) + '</div>';
    }
}

async function addPosition() {
    var ticker = document.getElementById("pf-ticker").value.trim().toUpperCase();
    var qty = parseFloat(document.getElementById("pf-qty").value);
    var price = parseFloat(document.getElementById("pf-price").value);
    var stop = parseFloat(document.getElementById("pf-stop").value);
    var buyDate = document.getElementById("pf-date").value;
    var segment = document.getElementById("pf-segment").value;
    if (!ticker || !qty || qty <= 0 || !price || price <= 0) {
        alert("Ticker, quantity and average price are required.");
        return;
    }
    var payload = {
        ticker: ticker, qty: qty, avg_price: price, segment: segment,
        buy_date: buyDate || new Date().toISOString().slice(0, 10),
    };
    if (stop && stop > 0) payload.stop_loss = stop;
    try {
        await fetchAPI_JSON("/api/portfolio", "POST", payload);
        document.getElementById("portfolio-form").reset();
        loadPortfolio();
    } catch (e) {
        alert("Failed to add: " + e.message);
    }
}

async function deletePosition(id) {
    if (!window.confirm("Remove this holding?")) return;
    try {
        await fetchAPI_JSON("/api/portfolio/" + id, "DELETE");
        loadPortfolio();
    } catch (e) {
        alert("Failed: " + e.message);
    }
}

async function editPosition(id) {
    var qty = window.prompt("New quantity:", "");
    if (qty == null) return;
    qty = parseFloat(qty);
    if (!qty || qty <= 0) return;
    var price = window.prompt("New average price:", "");
    if (price == null) return;
    price = parseFloat(price);
    if (!price || price <= 0) return;
    try {
        await fetchAPI_JSON("/api/portfolio/" + id, "PATCH", { qty: qty, avg_price: price });
        loadPortfolio();
    } catch (e) {
        alert("Failed: " + e.message);
    }
}

/* ─────── Init ─────── */
function init() {
    var page = getPage();
    loadOverview();
    initDropdown();
    initNewsClickDelegation();
    if (page === "dashboard") {
        initTabs();
        initCalculator();
        loadSignals();
    } else if (page === "chart") {
        initChartScanner();
        initChartSignals();
    } else if (page === "news") {
        loadNews();
    } else if (page === "journal") {
        initJournal();
    } else if (page === "sectors") {
        loadSectors();
    } else if (page === "flows") {
        loadFlows();
    } else if (page === "breadth") {
        loadBreadth();
    } else if (page === "stocks") {
        initStocks();
    } else if (page === "portfolio") {
        initPortfolio();
    }
    setInterval(loadOverview, 60000);
    if (page === "dashboard") setInterval(loadSignals, 300000);
    if (page === "stocks") setInterval(loadStocks, 60000);
    if (page === "portfolio") setInterval(loadPortfolio, 60000);
}

document.addEventListener("DOMContentLoaded", init);
