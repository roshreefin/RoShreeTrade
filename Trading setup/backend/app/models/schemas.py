from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal


class Signal(BaseModel):
    ticker: str
    segment: Literal["INTRADAY", "SWING", "LONG-TERM"]
    direction: Literal["BULLISH", "BEARISH"]
    action: Literal["BUY", "SHORT SELL"]
    entry_timestamp: Optional[str] = None
    entry_price: Optional[float] = None
    entry_range_low: Optional[float] = None
    entry_range_high: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    stop_loss: Optional[float] = None
    exit_time: Optional[str] = None
    signal_date: str
    confidence: Optional[float] = None
    strategy_name: str
    is_active: bool = True
    upside_pct: Optional[float] = None
    downside_pct: Optional[float] = None
    rr_ratio: Optional[float] = None
    chart_note: Optional[str] = None
    current_price: Optional[float] = None
    disclaimer: Optional[str] = None


class PositionSizingRecommendation(BaseModel):
    ticker: str
    entry_price: float
    stop_loss: float
    risk_per_share: float
    total_capital: float
    risk_percentage: float
    recommended_shares: int
    capital_at_risk: float


class NewsItem(BaseModel):
    id: str
    title: str
    source: str
    url: str
    published_at: str
    summary: Optional[str] = None
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = None
    affected_stocks: Optional[list[str]] = None
    sector: Optional[str] = None
    prediction: Optional[str] = None
    caution: Optional[str] = None
    dos: Optional[list[str]] = None
    donts: Optional[list[str]] = None


class MarketOverview(BaseModel):
    nifty_50: Optional[float] = None
    nifty_change_pct: Optional[float] = None
    bank_nifty: Optional[float] = None
    market_status: Literal["OPEN", "CLOSED", "PRE-MARKET", "POST-MARKET", "HOLIDAY", "WEEKEND"]
    advance_decline_ratio: Optional[str] = None
    last_updated: str


class ScanResult(BaseModel):
    signals: list[Signal]
    scan_timestamp: str
    market_status: str
    total_signals: int
    scanning: bool = False


class TechnicalAnalysis(BaseModel):
    ticker: str
    last_price: Optional[float] = None
    trend: str = "NEUTRAL"
    support: list[float] = []
    resistance: list[float] = []
    rsi: Optional[float] = None
    macd: Optional[str] = "NEEDS DATA"
    volume_analysis: Optional[str] = "UNAVAILABLE"
    pattern: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: int = 0
    data_available: bool = True
    signal: Optional[dict] = None
