import os
import sys
from pathlib import Path
from functools import partial

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncio
from datetime import datetime
from app.api.routes import router
from app.core.scanner import scanner
from app.data.market_data import market_data
from app.config import settings

scheduler = AsyncIOScheduler()


async def scheduled_scan():
    overview = await asyncio.to_thread(market_data.get_market_overview)
    if overview["market_status"] == "OPEN":
        result = await asyncio.to_thread(scanner.run_full_scan, overview["market_status"])
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete: {result.total_signals} signals found")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Market {overview['market_status']}. Scan skipped.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        scheduled_scan,
        IntervalTrigger(minutes=settings.SCAN_INTERVAL_MINUTES),
        id="signal_scanner",
        name="Scan for trading signals every N minutes",
    )
    scheduler.start()
    print(f"Signal scanner started. Scanning every {settings.SCAN_INTERVAL_MINUTES} minutes during market hours.")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="Equity Signal Engine - Indian Stock Market",
    description="Automated buy/sell signal generation for NSE/BSE Cash Equity segment",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router)

frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    page_map = {
        "/": "index.html",
        "/chart": "chart.html",
        "/news": "news.html",
        "/journal": "journal.html",
        "/stocks": "stocks.html",
        "/portfolio": "portfolio.html",
        "/sectors": "sectors.html",
        "/flows": "flows.html",
        "/breadth": "breadth.html",
        "/seasonal": "seasonal.html",
    }

    for route, filename in page_map.items():
        fn = filename
        app.add_api_route(route, lambda fn=fn: FileResponse(str(frontend_dir / fn)) if (frontend_dir / fn).exists() else JSONResponse({"error": f"{fn} not found"}, 404), methods=["GET"])


if __name__ == "__main__":
    import uvicorn
    reload = os.getenv("APP_RELOAD", "false").lower() == "true"
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
