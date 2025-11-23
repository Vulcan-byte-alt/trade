#!/usr/bin/env python3
"""Asymmetric Strategy - Different approaches for BTC vs ETH

BTC: Trend Rider (breakout and hold)
ETH: Dip Buyer (buy pullbacks with tight trailing stops)
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone, timedelta
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


class AsymmetricStrategy(BaseStrategy):
    """Asymmetric strategy: BTC uses trend following, ETH uses dip buying.

    BTC Strategy (Trend Rider):
    - Entry: 20-period breakout + EMA confirmation
    - Exit: 15% hard stop, 20% trailing

    ETH Strategy (Dip Buyer):
    - Entry: 2% dip from 3-day high
    - Exit: 15% trailing stop from peak
    """

    def __init__(self, config: Dict[str, Any], exchange):
        super().__init__(config=config, exchange=exchange)

        # Detect asset type (will be set on first price)
        self.is_btc: Optional[bool] = None

        # BTC parameters (Trend Rider)
        self.btc_fast_ema = int(config.get("btc_fast_ema_period", 20))
        self.btc_slow_ema = int(config.get("btc_slow_ema_period", 50))
        self.btc_breakout_period = int(config.get("btc_breakout_period", 20))
        self.btc_stop_loss = float(config.get("btc_stop_loss_pct", 0.15))
        self.btc_trailing_stop = float(config.get("btc_trailing_stop_pct", 0.20))
        self.btc_min_bars_between = int(config.get("btc_min_bars_between_trades", 50))

        # ETH parameters (Dip Buyer)
        self.eth_dip_threshold = float(config.get("eth_dip_threshold_pct", 0.020))  # 2.0%
        self.eth_lookback_hours = int(config.get("eth_lookback_hours", 72))  # 3 days
        self.eth_trailing_stop = float(config.get("eth_trailing_stop_pct", 0.15))  # 15%
        self.eth_cooldown_hours = int(config.get("eth_cooldown_hours", 12))

        # Common parameters
        self.position_pct = float(config.get("position_pct", 0.55))

        # State tracking
        self.entry_price: Optional[float] = None
        self.highest_price_since_entry: Optional[float] = None
        self.current_quantity: float = 0.0
        self.bars_since_last_trade: int = 0
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

    def _detect_asset_type(self, price: float):
        """Detect if this is BTC or ETH based on price."""
        if self.is_btc is None:
            self.is_btc = price > 10000  # BTC > $10k, ETH < $10k
            asset_name = "BTC" if self.is_btc else "ETH"
            self._logger.info(f"🔍 Detected asset: {asset_name} (price: ${price:.2f})")

    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate EMA."""
        if len(prices) < period:
            return None
        ema = mean(prices[:period])
        multiplier = 2 / (period + 1)
        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return ema

    def _is_breakout(self, prices: List[float], period: int) -> bool:
        """Check if current price breaks above recent high."""
        if len(prices) < period + 1:
            return False
        current = prices[-1]
        previous_high = max(prices[-(period+1):-1])
        return current > previous_high * 1.005

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

    # === BTC STRATEGY (TREND RIDER) ===
    def _btc_strategy(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """BTC: Breakout and hold with wide stops."""
        current_price = market.current_price
        prices = list(self.price_history)

        # Check exits first
        if portfolio.quantity > 0 and self.entry_price:
            pnl_pct = (current_price - self.entry_price) / self.entry_price

            # Calculate EMAs for trend reversal check
            slow_ema = self._calculate_ema(prices, self.btc_slow_ema)

            # Exit 1: Trend reversal (below slow EMA)
            if slow_ema and current_price < slow_ema:
                self._logger.info(f"BTC TREND REVERSAL: {pnl_pct*100:+.1f}%")
                return Signal("sell", size=portfolio.quantity,
                            reason=f"Trend reversal at {pnl_pct*100:+.1f}%",
                            entry_price=self.entry_price)

            # Exit 2: Hard stop loss
            if pnl_pct <= -self.btc_stop_loss:
                self._logger.info(f"BTC STOP LOSS: {pnl_pct*100:.1f}%")
                return Signal("sell", size=portfolio.quantity,
                            reason=f"Stop loss at {pnl_pct*100:.1f}%",
                            entry_price=self.entry_price)

            # Exit 3: Trailing stop
            if self.highest_price_since_entry:
                drawdown = (self.highest_price_since_entry - current_price) / self.highest_price_since_entry
                if drawdown >= self.btc_trailing_stop and pnl_pct > 0:
                    self._logger.info(f"BTC TRAILING STOP: {pnl_pct*100:+.1f}%")
                    return Signal("sell", size=portfolio.quantity,
                                reason=f"Trailing stop at +{pnl_pct*100:.1f}%",
                                entry_price=self.entry_price)

            return Signal("hold", reason=f"BTC riding: {pnl_pct*100:+.1f}%")

        # Check entries
        if portfolio.quantity > 0:
            return Signal("hold", reason="BTC position held")

        if self.bars_since_last_trade < self.btc_min_bars_between:
            return Signal("hold", reason=f"BTC cooldown: {self.bars_since_last_trade}/{self.btc_min_bars_between}")

        if len(prices) < self.btc_slow_ema:
            return Signal("hold", reason="BTC insufficient data")

        # Entry conditions
        fast_ema = self._calculate_ema(prices, self.btc_fast_ema)
        slow_ema = self._calculate_ema(prices, self.btc_slow_ema)

        if not fast_ema or not slow_ema:
            return Signal("hold", reason="BTC EMAs pending")

        is_breakout = self._is_breakout(prices, self.btc_breakout_period)
        price_above_slow = current_price > slow_ema * 1.02
        ema_bullish = fast_ema > slow_ema

        if is_breakout and price_above_slow and ema_bullish:
            position_value = portfolio.value(current_price) * self.position_pct
            position_value = min(position_value, portfolio.cash)
            size = position_value / current_price

            if size > 0:
                self._logger.info(f"🚀 BTC BUY: Breakout @ ${current_price:.2f}")
                return Signal("buy", size=size, reason="BTC breakout entry")

        return Signal("hold", reason="BTC waiting for setup")

    # === ETH STRATEGY (DIP BUYER) ===
    def _eth_strategy(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """ETH: Buy 2% dips from 3-day high with 15% trailing stop."""
        current_price = market.current_price
        current_time = market.timestamp or datetime.now(timezone.utc)

        # Check exits first
        if portfolio.quantity > 0 and self.entry_price:
            pnl_pct = (current_price - self.entry_price) / self.entry_price

            # Trailing stop (15%)
            if self.highest_price_since_entry:
                drawdown = (self.highest_price_since_entry - current_price) / self.highest_price_since_entry
                if drawdown >= self.eth_trailing_stop:
                    self._logger.info(f"ETH TRAILING STOP: {pnl_pct*100:+.1f}%")
                    return Signal("sell", size=portfolio.quantity,
                                reason=f"ETH trailing stop at {pnl_pct*100:+.1f}%",
                                entry_price=self.entry_price)

            return Signal("hold", reason=f"ETH holding: {pnl_pct*100:+.1f}%")

        # Check entries
        if portfolio.quantity > 0:
            return Signal("hold", reason="ETH position held")

        # Cooldown check
        if self.last_exit_time:
            hours_since_exit = (current_time - self.last_exit_time).total_seconds() / 3600
            if hours_since_exit < self.eth_cooldown_hours:
                return Signal("hold", reason=f"ETH cooldown: {hours_since_exit:.1f}/{self.eth_cooldown_hours}h")

        # Get 3-day high
        recent_high = self._get_recent_high(self.eth_lookback_hours, current_time)
        if not recent_high:
            return Signal("hold", reason="ETH insufficient history")

        # Check for dip
        dip_pct = (recent_high - current_price) / recent_high

        if dip_pct >= self.eth_dip_threshold:
            position_value = portfolio.value(current_price) * self.position_pct
            position_value = min(position_value, portfolio.cash)
            size = position_value / current_price

            if size > 0:
                self._logger.info(f"🎯 ETH BUY: {dip_pct*100:.1f}% dip @ ${current_price:.2f}")
                self._logger.info(f"   3-day high: ${recent_high:.2f}")
                return Signal("buy", size=size, reason=f"ETH dip buy: {dip_pct*100:.1f}%")

        return Signal("hold", reason=f"ETH waiting for dip (current: {dip_pct*100:.1f}%)")

    def generate_signal(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """Route to appropriate strategy based on asset type."""
        current_price = market.current_price
        current_time = market.timestamp or datetime.now(timezone.utc)

        # Detect asset type
        self._detect_asset_type(current_price)

        # Update price history
        self.price_history.append(current_price)
        self.price_timestamps.append(current_time)
        self.bars_since_last_trade += 1

        # Track highest price
        if portfolio.quantity > 0:
            if self.highest_price_since_entry is None or current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price
            self.current_quantity = portfolio.quantity

        # Route to appropriate strategy
        if self.is_btc:
            return self._btc_strategy(market, portfolio)
        else:
            return self._eth_strategy(market, portfolio)

    def on_trade(self, signal: Signal, execution_price: float, execution_size: float, timestamp: datetime) -> None:
        """Track trades and update state."""
        asset = "BTC" if self.is_btc else "ETH"

        if signal.action == "buy" and execution_size > 0:
            self.entry_price = execution_price
            self.highest_price_since_entry = execution_price
            self.current_quantity += execution_size
            self.bars_since_last_trade = 0
            self._logger.info(f"✅ {asset} ENTERED @ ${execution_price:.2f}")

        elif signal.action == "sell" and execution_size > 0:
            pnl = (execution_price - self.entry_price) * execution_size if self.entry_price else 0
            pnl_pct = ((execution_price - self.entry_price) / self.entry_price * 100) if self.entry_price else 0

            self._logger.info(f"✅ {asset} EXITED @ ${execution_price:.2f}")
            self._logger.info(f"   P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)")

            self.current_quantity -= execution_size
            if self.current_quantity <= 0:
                self.entry_price = None
                self.highest_price_since_entry = None
                self.current_quantity = 0.0
                self.last_exit_time = timestamp
            self.bars_since_last_trade = 0

    def get_state(self) -> Dict[str, Any]:
        """Return current strategy state."""
        return {
            "is_btc": self.is_btc,
            "entry_price": self.entry_price,
            "highest_price_since_entry": self.highest_price_since_entry,
            "current_quantity": self.current_quantity,
            "bars_since_last_trade": self.bars_since_last_trade,
            "last_exit_time": self.last_exit_time.isoformat() if self.last_exit_time else None,
            "price_history": list(self.price_history),
            "price_timestamps": [ts.isoformat() for ts in self.price_timestamps]
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore strategy state."""
        self.is_btc = state.get("is_btc")
        self.entry_price = state.get("entry_price")
        self.highest_price_since_entry = state.get("highest_price_since_entry")
        self.current_quantity = state.get("current_quantity", 0.0)
        self.bars_since_last_trade = state.get("bars_since_last_trade", 0)

        if state.get("last_exit_time"):
            self.last_exit_time = datetime.fromisoformat(state["last_exit_time"])

        if "price_history" in state:
            self.price_history = deque(state["price_history"], maxlen=200)

        if "price_timestamps" in state:
            self.price_timestamps = deque(
                [datetime.fromisoformat(ts) for ts in state["price_timestamps"]],
                maxlen=200
            )


# Register this strategy
register_strategy("asymmetric", AsymmetricStrategy)
