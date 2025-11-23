#!/usr/bin/env python3
"""ETH Dip Buyer Strategy - Buy 2% dips from 3-day high with 15% trailing stop"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from collections import deque
import logging

# Handle both local development and Docker container paths
base_path = os.path.join(os.path.dirname(__file__), '..', 'base-bot-template')
if not os.path.exists(base_path):
    base_path = '/app/base'

sys.path.insert(0, base_path)

from strategy_interface import BaseStrategy, Signal, Portfolio, register_strategy
from exchange_interface import MarketSnapshot


class EthDipBuyer(BaseStrategy):
    """Buy 2% dips from 3-day high, exit with 15% trailing stop.

    Entry: 2.0% dip from 72-hour high
    Exit: 15% trailing stop from highest price
    Cooldown: 12 hours after exit
    """

    def __init__(self, config: Dict[str, Any], exchange):
        super().__init__(config=config, exchange=exchange)

        # Parameters
        self.dip_threshold = float(config.get("dip_threshold_pct", 0.020))  # 2.0%
        self.lookback_hours = int(config.get("lookback_hours", 72))  # 3 days
        self.trailing_stop = float(config.get("trailing_stop_pct", 0.15))  # 15%
        self.cooldown_hours = int(config.get("cooldown_hours", 12))
        self.position_pct = float(config.get("position_pct", 0.55))

        # State
        self.entry_price: Optional[float] = None
        self.highest_price_since_entry: Optional[float] = None
        self.current_quantity: float = 0.0
        self.last_exit_time: Optional[datetime] = None

        # Price history
        self.price_history: deque = deque(maxlen=200)
        self.price_timestamps: deque = deque(maxlen=200)

        # Logging
        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(message)s'))
            self._logger.addHandler(handler)

    def _get_recent_high(self, hours: int, current_time: datetime) -> Optional[float]:
        """Get highest price in last N hours."""
        if not self.price_timestamps or not self.price_history:
            return None

        cutoff_time = current_time - timedelta(hours=hours)
        recent_prices = []

        for price, timestamp in zip(self.price_history, self.price_timestamps):
            if timestamp >= cutoff_time:
                recent_prices.append(price)

        return max(recent_prices) if recent_prices else None

    def generate_signal(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """Generate dip-buying signal."""
        current_price = market.current_price
        current_time = market.timestamp or datetime.now(timezone.utc)

        # Update history
        self.price_history.append(current_price)
        self.price_timestamps.append(current_time)

        # Track highest price if holding
        if portfolio.quantity > 0:
            if self.highest_price_since_entry is None or current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price
            self.current_quantity = portfolio.quantity

        # === EXIT LOGIC ===
        if portfolio.quantity > 0 and self.entry_price:
            pnl_pct = (current_price - self.entry_price) / self.entry_price

            # Trailing stop (15%)
            if self.highest_price_since_entry:
                drawdown = (self.highest_price_since_entry - current_price) / self.highest_price_since_entry
                if drawdown >= self.trailing_stop:
                    self._logger.info(f"TRAILING STOP: {pnl_pct*100:+.1f}%")
                    return Signal("sell", size=portfolio.quantity,
                                reason=f"Trailing stop at {pnl_pct*100:+.1f}%",
                                entry_price=self.entry_price)

            return Signal("hold", reason=f"Holding: {pnl_pct*100:+.1f}%")

        # === ENTRY LOGIC ===
        if portfolio.quantity > 0:
            return Signal("hold", reason="Position held")

        # Cooldown check
        if self.last_exit_time:
            hours_since_exit = (current_time - self.last_exit_time).total_seconds() / 3600
            if hours_since_exit < self.cooldown_hours:
                return Signal("hold", reason=f"Cooldown: {hours_since_exit:.1f}/{self.cooldown_hours}h")

        # Get 3-day high
        recent_high = self._get_recent_high(self.lookback_hours, current_time)
        if not recent_high:
            return Signal("hold", reason="Insufficient history")

        # Check for dip
        dip_pct = (recent_high - current_price) / recent_high

        if dip_pct >= self.dip_threshold:
            position_value = portfolio.value(current_price) * self.position_pct
            position_value = min(position_value, portfolio.cash)
            size = position_value / current_price

            if size > 0:
                self._logger.info(f"🎯 BUY: {dip_pct*100:.1f}% dip @ ${current_price:.2f}")
                self._logger.info(f"   3-day high: ${recent_high:.2f}")
                return Signal("buy", size=size, reason=f"Dip buy: {dip_pct*100:.1f}%")

        return Signal("hold", reason=f"Waiting for dip (current: {dip_pct*100:.1f}%)")

    def on_trade(self, signal: Signal, execution_price: float, execution_size: float, timestamp: datetime) -> None:
        """Track trades."""
        if signal.action == "buy" and execution_size > 0:
            self.entry_price = execution_price
            self.highest_price_since_entry = execution_price
            self.current_quantity += execution_size
            self._logger.info(f"✅ ENTERED @ ${execution_price:.2f}")

        elif signal.action == "sell" and execution_size > 0:
            pnl = (execution_price - self.entry_price) * execution_size if self.entry_price else 0
            pnl_pct = ((execution_price - self.entry_price) / self.entry_price * 100) if self.entry_price else 0

            self._logger.info(f"✅ EXITED @ ${execution_price:.2f}")
            self._logger.info(f"   P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)")

            self.current_quantity -= execution_size
            if self.current_quantity <= 0:
                self.entry_price = None
                self.highest_price_since_entry = None
                self.current_quantity = 0.0
                self.last_exit_time = timestamp

    def get_state(self) -> Dict[str, Any]:
        """Return state."""
        return {
            "entry_price": self.entry_price,
            "highest_price_since_entry": self.highest_price_since_entry,
            "current_quantity": self.current_quantity,
            "last_exit_time": self.last_exit_time.isoformat() if self.last_exit_time else None,
            "price_history": list(self.price_history),
            "price_timestamps": [ts.isoformat() for ts in self.price_timestamps]
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore state."""
        self.entry_price = state.get("entry_price")
        self.highest_price_since_entry = state.get("highest_price_since_entry")
        self.current_quantity = state.get("current_quantity", 0.0)

        if state.get("last_exit_time"):
            self.last_exit_time = datetime.fromisoformat(state["last_exit_time"])

        if "price_history" in state:
            self.price_history = deque(state["price_history"], maxlen=200)

        if "price_timestamps" in state:
            self.price_timestamps = deque(
                [datetime.fromisoformat(ts) for ts in state["price_timestamps"]],
                maxlen=200
            )


# Register strategy
register_strategy("eth_dip_buyer", EthDipBuyer)
