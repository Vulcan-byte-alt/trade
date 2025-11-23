#!/usr/bin/env python3
"""Trend Rider Strategy - Buy the Trend and HOLD

Philosophy: The market went up 60% in Jan-Jun 2024. We need to CAPTURE that, not trade around it.

Strategy:
- Make FEWER trades (5-10 total, not 100!)
- HOLD through volatility with wide stops
- Only exit on major trend reversals
- Think position trading, not swing trading

Entry: Major breakout confirmed by multiple timeframes
Exit: Only when trend clearly reverses
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import deque
from statistics import mean, stdev
import logging

# Handle both local development and Docker container paths
base_path = os.path.join(os.path.dirname(__file__), '..', 'base-bot-template')
if not os.path.exists(base_path):
    base_path = '/app/base'

sys.path.insert(0, base_path)

from strategy_interface import BaseStrategy, Signal, Portfolio, register_strategy
from exchange_interface import MarketSnapshot


class TrendRiderStrategy(BaseStrategy):
    """Buy the trend and HOLD. Fewer trades, bigger wins.

    Core Principle: If BTC is going from $44k to $71k, we want to be IN for most of that ride,
    not trading in and out 100 times and missing the real move.

    Entry Rules:
    - Price breaks above 20-period high (major breakout)
    - Price well above EMA(50) - confirmed uptrend
    - No position currently held

    Exit Rules:
    - Price breaks below EMA(50) (trend over)
    - OR 15% stop loss (catastrophic failure)
    - OR 20% trailing stop from highest point (lock in gains)

    Position: Max 55% per trade
    """

    def __init__(self, config: Dict[str, Any], exchange):
        super().__init__(config=config, exchange=exchange)

        # Trend detection - slower is better for position trading
        self.fast_ema_period = int(config.get("fast_ema_period", 20))
        self.slow_ema_period = int(config.get("slow_ema_period", 50))

        # Breakout confirmation
        self.breakout_period = int(config.get("breakout_period", 20))  # 20-period high

        # Position sizing
        self.position_pct = float(config.get("position_pct", 0.55))

        # Exit rules - WIDE to hold through volatility
        self.stop_loss_pct = float(config.get("stop_loss_pct", 0.15))  # 15% hard stop
        self.trailing_stop_pct = float(config.get("trailing_stop_pct", 0.20))  # 20% trailing

        # Trade frequency - VERY LIMITED
        self.min_bars_between_trades = int(config.get("min_bars_between_trades", 50))  # ~2 days at hourly

        # State tracking
        self.entry_price: Optional[float] = None
        self.highest_price_since_entry: Optional[float] = None
        self.current_quantity: float = 0.0
        self.bars_since_last_trade: int = 0
        self.last_trade_timestamp: Optional[datetime] = None

        # Price history for calculations
        self.price_history: deque = deque(maxlen=max(self.slow_ema_period, self.breakout_period) + 10)

        # Logging
        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self._logger.addHandler(handler)

    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate EMA for given period."""
        if len(prices) < period:
            return None

        # Start with SMA
        ema = mean(prices[:period])
        multiplier = 2 / (period + 1)

        # Calculate EMA
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def _is_breakout(self, prices: List[float], period: int) -> bool:
        """Check if current price is breaking out to new high."""
        if len(prices) < period + 1:
            return False

        current_price = prices[-1]
        previous_highs = prices[-(period+1):-1]
        highest_previous = max(previous_highs)

        # Must break above previous high by at least 0.5%
        return current_price > highest_previous * 1.005

    def generate_signal(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """Generate trading signal based on trend riding logic."""

        # Update price history
        current_price = market.current_price
        self.price_history.append(current_price)
        self.bars_since_last_trade += 1

        # Track highest price if holding position
        if portfolio.quantity > 0:
            if self.highest_price_since_entry is None or current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price
            self.current_quantity = portfolio.quantity

        # Not enough data yet
        if len(self.price_history) < self.slow_ema_period:
            return Signal("hold", reason="Insufficient data for trend analysis")

        prices = list(self.price_history)

        # Calculate EMAs
        fast_ema = self._calculate_ema(prices, self.fast_ema_period)
        slow_ema = self._calculate_ema(prices, self.slow_ema_period)

        if fast_ema is None or slow_ema is None:
            return Signal("hold", reason="EMA calculation pending")

        # === EXIT LOGIC (check first) ===
        if portfolio.quantity > 0 and self.entry_price:
            pnl_pct = (current_price - self.entry_price) / self.entry_price

            # Exit 1: Price breaks below slow EMA (trend reversal)
            if current_price < slow_ema:
                self._logger.info(f"TREND REVERSAL: Price {current_price:.2f} < EMA({self.slow_ema_period}) {slow_ema:.2f}")
                return Signal("sell", size=portfolio.quantity,
                            reason=f"Trend reversal - exit at {pnl_pct*100:+.1f}%",
                            entry_price=self.entry_price)

            # Exit 2: Hard stop loss (15% drawdown)
            if pnl_pct <= -self.stop_loss_pct:
                self._logger.info(f"STOP LOSS HIT: {pnl_pct*100:.1f}%")
                return Signal("sell", size=portfolio.quantity,
                            reason=f"Stop loss at {pnl_pct*100:.1f}%",
                            entry_price=self.entry_price)

            # Exit 3: Trailing stop (20% from peak)
            if self.highest_price_since_entry:
                drawdown_from_peak = (self.highest_price_since_entry - current_price) / self.highest_price_since_entry
                if drawdown_from_peak >= self.trailing_stop_pct and pnl_pct > 0:
                    self._logger.info(f"TRAILING STOP: {drawdown_from_peak*100:.1f}% from peak, profit {pnl_pct*100:.1f}%")
                    return Signal("sell", size=portfolio.quantity,
                                reason=f"Trailing stop at +{pnl_pct*100:.1f}%",
                                entry_price=self.entry_price)

            # Still holding
            return Signal("hold", reason=f"Riding trend: {pnl_pct*100:+.1f}%")

        # === ENTRY LOGIC ===
        # Already holding? Don't enter again
        if portfolio.quantity > 0:
            return Signal("hold", reason="Position already held")

        # Respect minimum time between trades
        if self.bars_since_last_trade < self.min_bars_between_trades:
            return Signal("hold", reason=f"Cooldown: {self.bars_since_last_trade}/{self.min_bars_between_trades} bars")

        # Entry conditions:
        # 1. Major breakout (new 20-period high)
        # 2. Price well above slow EMA (confirmed uptrend)
        # 3. Fast EMA above slow EMA (trend strength)

        is_breakout = self._is_breakout(prices, self.breakout_period)
        price_above_slow_ema = current_price > slow_ema * 1.02  # At least 2% above
        ema_bullish = fast_ema > slow_ema

        if is_breakout and price_above_slow_ema and ema_bullish:
            # Calculate position size
            position_value = portfolio.value(current_price) * self.position_pct
            position_value = min(position_value, portfolio.cash)
            size = position_value / current_price

            if size > 0:
                self._logger.info(f"🚀 BUY SIGNAL: Major breakout @ {current_price:.2f}")
                self._logger.info(f"   Fast EMA: {fast_ema:.2f}, Slow EMA: {slow_ema:.2f}")
                self._logger.info(f"   {self.breakout_period}-period breakout confirmed")
                return Signal("buy", size=size,
                            reason=f"Major trend breakout - {self.breakout_period}period high")

        return Signal("hold", reason="Waiting for breakout setup")

    def on_trade(self, signal: Signal, execution_price: float, execution_size: float, timestamp: datetime) -> None:
        """Track trades and update state."""
        if signal.action == "buy" and execution_size > 0:
            self.entry_price = execution_price
            self.highest_price_since_entry = execution_price
            self.current_quantity += execution_size
            self.bars_since_last_trade = 0
            self.last_trade_timestamp = timestamp
            self._logger.info(f"✅ ENTERED: {execution_size:.4f} @ ${execution_price:.2f}")

        elif signal.action == "sell" and execution_size > 0:
            pnl = (execution_price - self.entry_price) * execution_size if self.entry_price else 0
            pnl_pct = ((execution_price - self.entry_price) / self.entry_price * 100) if self.entry_price else 0

            self._logger.info(f"✅ EXITED: {execution_size:.4f} @ ${execution_price:.2f}")
            self._logger.info(f"   P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)")

            # Reset state
            self.current_quantity -= execution_size
            if self.current_quantity <= 0:
                self.entry_price = None
                self.highest_price_since_entry = None
                self.current_quantity = 0.0
            self.bars_since_last_trade = 0
            self.last_trade_timestamp = timestamp

    def get_state(self) -> Dict[str, Any]:
        """Return current strategy state."""
        return {
            "entry_price": self.entry_price,
            "highest_price_since_entry": self.highest_price_since_entry,
            "current_quantity": self.current_quantity,
            "bars_since_last_trade": self.bars_since_last_trade,
            "price_history": list(self.price_history)
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore strategy state."""
        self.entry_price = state.get("entry_price")
        self.highest_price_since_entry = state.get("highest_price_since_entry")
        self.current_quantity = state.get("current_quantity", 0.0)
        self.bars_since_last_trade = state.get("bars_since_last_trade", 0)
        if "price_history" in state:
            self.price_history = deque(state["price_history"],
                                       maxlen=max(self.slow_ema_period, self.breakout_period) + 10)


# Register this strategy
register_strategy("trend_rider", TrendRiderStrategy)
