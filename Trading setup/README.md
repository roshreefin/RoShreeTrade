# Equity Signal Engine — Indian Stock Market

Automated buy/sell signal generation for NSE/BSE Cash (Equity) segment.

## Three Strategies

| Strategy | Segment | Universe | Timeframe |
|---|---|---|---|
| High-RVOL VWAP Pullback | Intraday | Nifty 200 | 9:45 AM – 3:15 PM |
| Volatility Contraction Pattern (VCP) | Swing | Nifty 500 | Multi-day/weeks |
| Stage 2 Mark-Up Breakout | Long-Term | NSE Cash | 6 mo – 3 yr |

## Quick Start

```bash
cd backend
pip install -r requirements.txt
python -m app.main
```

Open http://localhost:8000 in your browser.

## Features

- Live signal scanning every 15 minutes during market hours
- ATR-based dynamic stop losses
- Position size calculator (1% risk model)
- Indian stock market news from Moneycontrol, ET, Livemint
- Kite Connect API ready (falls back to yfinance for dev)

## Configuration

Copy `.env.example` to `.env` and set your Zerodha Kite Connect keys:
- `KITE_API_KEY` / `KITE_ACCESS_TOKEN` — real-time data
- `USE_YFINANCE_FALLBACK=true` — uses free Yahoo Finance (delayed)

## Risk Warning

Trading involves substantial risk. This tool generates signals based on technical patterns — always do your own due diligence.
