import math
from app.models.schemas import PositionSizingRecommendation, Signal


class RiskEngine:
    def calculate_atr_stop(self, entry_price: float, atr: float, multiplier: float = 1.5) -> float:
        return entry_price - (multiplier * atr)

    def calculate_position_size(
        self,
        total_capital: float,
        entry_price: float,
        stop_loss: float,
        risk_percentage: float = 0.01,
    ) -> PositionSizingRecommendation:
        risk_per_share = abs(entry_price - stop_loss)
        capital_at_risk = total_capital * risk_percentage

        if risk_per_share <= 0:
            return PositionSizingRecommendation(
                ticker="",
                entry_price=entry_price,
                stop_loss=stop_loss,
                risk_per_share=0,
                total_capital=total_capital,
                risk_percentage=risk_percentage * 100,
                recommended_shares=0,
                capital_at_risk=capital_at_risk,
            )

        shares = math.floor(capital_at_risk / risk_per_share)
        actual_risk = shares * risk_per_share

        return PositionSizingRecommendation(
            ticker="",
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_per_share=round(risk_per_share, 2),
            total_capital=total_capital,
            risk_percentage=risk_percentage * 100,
            recommended_shares=shares,
            capital_at_risk=round(actual_risk, 2),
        )

    def format_signal_message(self, signal: Signal, capital: float = 10_00_000) -> str:
        direction_emoji = "🟢" if signal.direction == "BULLISH" else "🔴"
        msg = f"""
{direction_emoji} *{signal.ticker} - {signal.segment} | {signal.direction}*

📊 *Strategy:* {signal.strategy_name}
🎯 *Entry:* ₹{signal.entry_price}
📏 *Entry Range:* ₹{signal.entry_range_low} - ₹{signal.entry_range_high}
🎯 *Target 1:* ₹{signal.target_1}
🎯 *Target 2:* ₹{signal.target_2 or 'Trail'}
🛑 *Stop Loss:* ₹{signal.stop_loss}
⏰ *Exit:* {signal.exit_time}
⚡ *Confidence:* {signal.confidence}%
"""
        if capital and signal.entry_price and signal.stop_loss:
            sizing = self.calculate_position_size(capital, signal.entry_price, signal.stop_loss)
            msg += f"\n💼 *Capital: ₹{capital:,.0f} | Risk: 1%*"
            action_label = "Buy" if signal.action == "BUY" else "Short Sell"
            msg += f"\n📝 *{action_label} {sizing.recommended_shares} shares @ ~₹{signal.entry_range_low}-{signal.entry_range_high}*"

        return msg


risk_engine = RiskEngine()
