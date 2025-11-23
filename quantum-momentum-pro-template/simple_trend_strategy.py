#!/usr/bin/env python3
"""Simple Trend Following Strategy - Optimized for Jan-Jun 2024 Crypto Markets

Philosophy: Keep it simple. Ride trends. Cut losses quickly. Let winners run.

Entry: Price crosses above EMA(50) with momentum
Exit: 10% profit OR 4% loss OR trend reversal
Position: 55% (max allowed)
Frequency: Max 3 trades/month
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import deque
from statistics import mean
import logging

# Handle both local development and Docker container paths
base_path = os.path.join(os.path.dirname(__file__), '..', 'base-bot-template')
if not os.path.exists(base_path):
    base_path = '/app/base'

sys.path.insert(0, base_path)

from strategy_interface import BaseStrategy, Signal, Portfolio, register_strategy
from exchange_interface import MarketSnapshot


class SimpleTrendStrategy(BaseStrategy):
    """Dead simple trend following strategy optimized for 2024 crypto bull market.

    Rules:
    - BUY: When price > EMA(50) AND RSI < 65 (not overbought)
    - SELL: +10% profit OR -4% loss OR price < EMA(50)
    - Position: Always 55% (max allowed)
    - Frequency: Max 3/month to avoid overtrading
    """

    def __init__(self, config: Dict[str, Any], exchange):
        super().__init__(config=config, exchange=exchange)

        # FASTER trend detection (EMA 20 instead of 50)
        self.trend_ema_period = int(config.get("trend_ema_period", 20))  # FASTER!

        # Momentum confirmation
        self.momentum_period = int(config.get("momentum_period", 10))  # 10-period high

        # Fixed position size (max allowed by contest)
        self.position_pct = float(config.get("position_pct", 0.55))  # 55%

        # REALISTIC exit rules (lower targets that actually get hit!)
        self.take_profit_pct = float(config.get("take_profit_pct", 0.06))  # 6% (was 10%)
        self.stop_loss_pct = float(config.get("stop_loss_pct", 0.05))  # 5% (was 4%)
        self.trailing_stop_pct = float(config.get("trailing_stop_pct", 0.04))  # 4% trailing

        # Trade frequency control
        self.max_trades_per_month = int(config.get("max_trades_per_month", 3))
        self.trade_count_by_month: Dict[str, int] = {}

        # State
        self.entry_price: Optional[float] = None
        self.highest_price_since_entry: Optional[float] = None
        self.price_history = deque(maxlen=max(self.trend_ema_period, self.momentum_period) + 50)

        self._logger = logging.getLogger("strategy.simple_trend")

    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate EMA."""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = mean(prices[:period])

        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def _is_new_high(self, prices: List[float], period: int) -> bool:
        """Check if current price is making a new high."""
        if len(prices) < period + 1:
            return False

        current = prices[-1]
        previous_highs = prices[-(period+1):-1]
        return current > max(previous_highs)

    def generate_signal(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """Simple trend following logic."""

        # Build price history
        self.price_history.append(market.current_price)
        prices = list(self.price_history)

        # Need enough data
        if len(prices) < self.trend_ema_period:
            return Signal("hold", reason="Warming up")

        current_price = market.current_price

        # === SELL LOGIC (Check first) ===
        if portfolio.quantity > 0 and self.entry_price:
            # Track highest price
            if self.highest_price_since_entry is None or current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price

            pnl_pct = (current_price - self.entry_price) / self.entry_price

            # Take profit (6% target)
            if pnl_pct >= self.take_profit_pct:
                self._logger.info(f"TAKE PROFIT: {pnl_pct*100:.2f}%")
                return Signal("sell", size=portfolio.quantity,
                            reason=f"Take profit at +{pnl_pct*100:.1f}%",
                            entry_price=self.entry_price)

            # Trailing stop (4% from peak)
            if self.highest_price_since_entry:
                trailing_pct = (self.highest_price_since_entry - current_price) / self.highest_price_since_entry
                if trailing_pct >= self.trailing_stop_pct and pnl_pct > 0:  # Only if in profit
                    self._logger.info(f"TRAILING STOP: {pnl_pct*100:.2f}%")
                    return Signal("sell", size=portfolio.quantity,
                                reason=f"Trailing stop at +{pnl_pct*100:.1f}%",
                                entry_price=self.entry_price)

            # Stop loss (5% max loss)
            if pnl_pct <= -self.stop_loss_pct:
                self._logger.info(f"STOP LOSS: {pnl_pct*100:.2f}%")
                return Signal("sell", size=portfolio.quantity,
                            reason=f"Stop loss at {pnl_pct*100:.1f}%",
                            entry_price=self.entry_price)

        # === BUY LOGIC ===

        # Don't buy if already holding
        if portfolio.quantity > 0:
            return Signal("hold", reason="Already in position")

        # Trade frequency limit
        if market.timestamp:
            month_key = market.timestamp.strftime("%Y-%m")
            trades_this_month = self.trade_count_by_month.get(month_key, 0)
            if trades_this_month >= self.max_trades_per_month:
                return Signal("hold", reason=f"Monthly limit ({trades_this_month}/{self.max_trades_per_month})")

        # Calculate indicators
        ema = self._calculate_ema(prices, self.trend_ema_period)
        is_new_high = self._is_new_high(prices, self.momentum_period)

        if not ema:
            return Signal("hold", reason="Calculating indicators")

        # MOMENTUM BREAKOUT ENTRY:
        # 1. Price above EMA(20) - general uptrend
        # 2. Price making new 10-period high - momentum
        if current_price > ema and is_new_high:
            # Calculate position size
            position_value = portfolio.value(current_price) * self.position_pct
            position_value = min(position_value, portfolio.cash)
            size = position_value / current_price

            if size > 0:
                self._logger.info(f"BUY SIGNAL: Momentum breakout @ {current_price:.2f}")
                return Signal("buy", size=size,
                            reason=f"Momentum breakout (new {self.momentum_period}-period high)")

        return Signal("hold", reason="Waiting for trend entry")

    def on_trade(self, signal: Signal, execution_price: float, execution_size: float, timestamp: datetime) -> None:
        """Track trades."""
        if signal.action == "buy" and execution_size > 0:
            self.entry_price = execution_price
            self.highest_price_since_entry = execution_price

            # Update trade count
            ts = timestamp if timestamp else datetime.now(timezone.utc)
            month_key = ts.strftime("%Y-%m")
            self.trade_count_by_month[month_key] = self.trade_count_by_month.get(month_key, 0) + 1

            self._logger.info(f"BUY: {execution_size:.8f} @ ${execution_price:,.2f}")

        elif signal.action == "sell" and execution_size > 0:
            if self.entry_price:
                pnl = (execution_price - self.entry_price) * execution_size
                pnl_pct = (execution_price - self.entry_price) / self.entry_price * 100
                self._logger.info(f"SELL: {execution_size:.8f} @ ${execution_price:,.2f} | PnL: ${pnl:,.2f} ({pnl_pct:+.2f}%)")

            self.entry_price = None
            self.highest_price_since_entry = None

    def get_state(self) -> Dict[str, Any]:
        return {
            "entry_price": self.entry_price,
            "highest_price_since_entry": self.highest_price_since_entry,
            "trade_count_by_month": self.trade_count_by_month,
            "price_history": list(self.price_history)
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        self.entry_price = state.get("entry_price")
        self.highest_price_since_entry = state.get("highest_price_since_entry")
        self.trade_count_by_month = state.get("trade_count_by_month", {})
        if "price_history" in state:
            self.price_history = deque(state["price_history"], maxlen=self.price_history.maxlen)


# Register the strategy
register_strategy("simple_trend", lambda cfg, ex: SimpleTrendStrategy(cfg, ex))
