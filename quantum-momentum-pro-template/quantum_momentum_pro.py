#!/usr/bin/env python3
"""Quantum Momentum Pro Strategy - Advanced Multi-Indicator Trading System.

This strategy combines multiple technical indicators for high-probability entries:
- Triple EMA system (trend direction)
- RSI (momentum oscillator)
- MACD (trend confirmation)
- Bollinger Bands (volatility-based entries)
- ATR-based position sizing and stop losses
- Dynamic take profit levels
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Deque
from collections import deque
from statistics import mean, pstdev
import logging

# Handle both local development and Docker container paths
base_path = os.path.join(os.path.dirname(__file__), '..', 'base-bot-template')
if not os.path.exists(base_path):
    base_path = '/app/base'

sys.path.insert(0, base_path)

from strategy_interface import BaseStrategy, Signal, Portfolio, register_strategy
from exchange_interface import MarketSnapshot


class QuantumMomentumProStrategy(BaseStrategy):
    """Advanced multi-indicator trading strategy optimized for trend-following with mean reversion.

    This strategy uses a sophisticated combination of technical indicators:
    1. Triple EMA system for trend identification
    2. RSI for momentum confirmation
    3. MACD for trend strength
    4. Bollinger Bands for entry timing
    5. ATR for dynamic position sizing and risk management
    6. Multi-level take profit system

    Optimized for hourly data on BTC-USD and ETH-USD.
    """

    def __init__(self, config: Dict[str, Any], exchange):
        super().__init__(config=config, exchange=exchange)

        # Moving Average periods
        self.ema_fast = int(config.get("ema_fast", 20))
        self.ema_medium = int(config.get("ema_medium", 50))
        self.ema_slow = int(config.get("ema_slow", 100))

        # RSI configuration
        self.rsi_period = int(config.get("rsi_period", 14))
        self.rsi_oversold = float(config.get("rsi_oversold", 35))
        self.rsi_overbought = float(config.get("rsi_overbought", 70))

        # MACD configuration
        self.macd_fast = int(config.get("macd_fast", 12))
        self.macd_slow = int(config.get("macd_slow", 26))
        self.macd_signal = int(config.get("macd_signal", 9))

        # Bollinger Bands
        self.bb_period = int(config.get("bb_period", 20))
        self.bb_std = float(config.get("bb_std", 2.0))

        # ATR for volatility
        self.atr_period = int(config.get("atr_period", 14))

        # Position sizing
        self.base_position_pct = float(config.get("base_position_pct", 0.45))  # 45% base
        self.max_position_pct = float(config.get("max_position_pct", 0.55))  # 55% max
        self.min_position_pct = float(config.get("min_position_pct", 0.40))  # 40% min (increased from 30%)

        # Risk management
        self.stop_loss_atr_multiplier = float(config.get("stop_loss_atr_multiplier", 2.5))  # Increased from 2.0
        self.take_profit_levels = [
            float(config.get("tp_level_1", 0.08)),  # 8% (increased from 5%)
            float(config.get("tp_level_2", 0.12)),  # 12% (increased from 8%)
            float(config.get("tp_level_3", 0.18)),  # 18% (increased from 12%)
        ]
        self.trailing_stop_pct = float(config.get("trailing_stop_pct", 0.06))  # 6% (increased from 4%)

        # Signal strength threshold
        self.min_signal_strength = float(config.get("min_signal_strength", 0.70))  # 70% (increased from 50%)

        # Max drawdown protection
        self.max_drawdown_pct = float(config.get("max_drawdown_pct", 0.35))  # 35%

        # Trade frequency control
        self.min_hours_between_trades = int(config.get("min_hours_between_trades", 24))  # At least 24 hours between trades

        # State tracking
        self.positions: Deque[Dict[str, Any]] = deque()
        self.entry_price: Optional[float] = None
        self.highest_price_since_entry: Optional[float] = None
        self.starting_portfolio_value: Optional[float] = None
        self.current_quantity: float = 0.0  # Track our position size
        self.last_trade_time: Optional[datetime] = None  # Track last trade timestamp

        # Price history for indicators
        self.price_history: Deque[float] = deque(maxlen=max(self.ema_slow, self.bb_period, self.atr_period) + 50)

        # Logging
        self._logger = logging.getLogger("strategy.quantum_momentum_pro")

    def prepare(self) -> None:
        """Warm-up phase - collect initial price data."""
        self._logger.info("Quantum Momentum Pro Strategy initialized and ready")

    # ==================== INDICATOR CALCULATIONS ====================

    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = mean(prices[:period])  # Start with SMA

        for price in prices[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index."""
        if len(prices) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) < period:
            return None

        avg_gain = mean(gains[-period:])
        avg_loss = mean(losses[-period:])

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_macd(self, prices: List[float]) -> Optional[Dict[str, float]]:
        """Calculate MACD (Moving Average Convergence Divergence)."""
        if len(prices) < self.macd_slow:
            return None

        ema_fast = self._calculate_ema(prices, self.macd_fast)
        ema_slow = self._calculate_ema(prices, self.macd_slow)

        if ema_fast is None or ema_slow is None:
            return None

        macd_line = ema_fast - ema_slow

        # For signal line, we need MACD history
        # Simplified: using current MACD as both line and signal for first calculation
        # In production, maintain MACD history

        return {
            "macd": macd_line,
            "signal": macd_line * 0.9,  # Simplified
            "histogram": macd_line * 0.1
        }

    def _calculate_bollinger_bands(self, prices: List[float]) -> Optional[Dict[str, float]]:
        """Calculate Bollinger Bands."""
        if len(prices) < self.bb_period:
            return None

        recent_prices = prices[-self.bb_period:]
        sma = mean(recent_prices)
        std_dev = pstdev(recent_prices)

        return {
            "upper": sma + (self.bb_std * std_dev),
            "middle": sma,
            "lower": sma - (self.bb_std * std_dev)
        }

    def _calculate_atr(self, prices: List[float]) -> Optional[float]:
        """Calculate Average True Range (simplified using price ranges)."""
        if len(prices) < self.atr_period + 1:
            return None

        true_ranges = []
        for i in range(1, len(prices)):
            high_low = abs(prices[i] - prices[i-1])
            true_ranges.append(high_low)

        if len(true_ranges) < self.atr_period:
            return None

        atr = mean(true_ranges[-self.atr_period:])
        return atr

    # ==================== SIGNAL GENERATION ====================

    def _calculate_signal_strength(self, market: MarketSnapshot) -> float:
        """Calculate signal strength from 0.0 to 1.0 based on indicator confluence."""
        prices = list(self.price_history) + [market.current_price]

        if len(prices) < self.ema_slow:
            return 0.0

        strength = 0.0
        max_strength = 6.0  # Number of indicators

        # 1. Triple EMA alignment
        ema_fast = self._calculate_ema(prices, self.ema_fast)
        ema_medium = self._calculate_ema(prices, self.ema_medium)
        ema_slow = self._calculate_ema(prices, self.ema_slow)

        if ema_fast and ema_medium and ema_slow:
            # Bullish: fast > medium > slow
            if ema_fast > ema_medium > ema_slow:
                strength += 1.0
            elif ema_fast > ema_medium:
                strength += 0.5

        # 2. RSI
        rsi = self._calculate_rsi(prices, self.rsi_period)
        if rsi:
            if rsi < self.rsi_oversold:
                strength += 1.0  # Strong buy signal
            elif rsi < 50:
                strength += 0.5  # Moderate buy signal

        # 3. MACD
        macd = self._calculate_macd(prices)
        if macd and macd["macd"] > macd["signal"]:
            strength += 1.0

        # 4. Bollinger Bands
        bb = self._calculate_bollinger_bands(prices)
        if bb:
            # Price near lower band = buy signal
            if market.current_price <= bb["lower"]:
                strength += 1.0
            elif market.current_price < bb["middle"]:
                strength += 0.5

        # 5. Price momentum (recent trend)
        if len(prices) >= 10:
            recent_change = (prices[-1] - prices[-10]) / prices[-10]
            if recent_change > 0:
                strength += 1.0
            elif recent_change > -0.02:  # Small dip
                strength += 0.5

        # 6. Volatility (ATR) - lower volatility = higher confidence
        atr = self._calculate_atr(prices)
        if atr:
            volatility_pct = atr / market.current_price
            if volatility_pct < 0.02:  # Low volatility
                strength += 1.0
            elif volatility_pct < 0.04:
                strength += 0.5

        return min(strength / max_strength, 1.0)

    def _should_buy(self, market: MarketSnapshot, portfolio: Portfolio) -> tuple[bool, float, str]:
        """Determine if we should buy and with what position size."""
        prices = list(self.price_history) + [market.current_price]

        # Need minimum data
        if len(prices) < self.ema_slow:
            return False, 0.0, "Insufficient data for indicators"

        # Trade frequency cooldown (prevent overtrading)
        if self.last_trade_time and market.timestamp:
            hours_since_last_trade = (market.timestamp - self.last_trade_time).total_seconds() / 3600
            if hours_since_last_trade < self.min_hours_between_trades:
                return False, 0.0, f"Cooldown active: {hours_since_last_trade:.1f}h / {self.min_hours_between_trades}h"

        # Don't buy if we have significant holdings
        current_value = portfolio.value(market.current_price)
        position_value = portfolio.quantity * market.current_price
        position_pct = position_value / current_value if current_value > 0 else 0

        if position_pct > 0.7:  # Already 70% invested
            return False, 0.0, "Position limit reached"

        # Check drawdown protection
        if self.starting_portfolio_value:
            drawdown = (self.starting_portfolio_value - current_value) / self.starting_portfolio_value
            if drawdown > self.max_drawdown_pct:
                return False, 0.0, f"Drawdown protection active: {drawdown*100:.2f}%"

        # Calculate indicators
        ema_fast = self._calculate_ema(prices, self.ema_fast)
        ema_medium = self._calculate_ema(prices, self.ema_medium)
        ema_slow = self._calculate_ema(prices, self.ema_slow)
        rsi = self._calculate_rsi(prices, self.rsi_period)
        macd = self._calculate_macd(prices)
        bb = self._calculate_bollinger_bands(prices)

        # Core buy conditions
        bullish_trend = ema_fast and ema_medium and ema_fast > ema_medium
        rsi_not_overbought = rsi and rsi < self.rsi_overbought
        macd_bullish = macd and macd["macd"] > macd["signal"]

        if not (bullish_trend and rsi_not_overbought):
            return False, 0.0, "Trend conditions not met"

        # Calculate signal strength for position sizing
        signal_strength = self._calculate_signal_strength(market)

        # Require minimum signal strength (70% for quality trades)
        if signal_strength < self.min_signal_strength:
            return False, 0.0, f"Signal strength too low: {signal_strength*100:.1f}% (min: {self.min_signal_strength*100:.0f}%)"

        # Dynamic position sizing based on signal strength
        position_pct = self.min_position_pct + (signal_strength * (self.max_position_pct - self.min_position_pct))
        position_pct = min(position_pct, self.max_position_pct)

        return True, position_pct, f"BUY signal (strength: {signal_strength*100:.1f}%, position: {position_pct*100:.1f}%)"

    def _should_sell(self, market: MarketSnapshot, portfolio: Portfolio) -> tuple[bool, float, str]:
        """Determine if we should sell."""
        if portfolio.quantity <= 0 or self.entry_price is None:
            return False, 0.0, "No position to sell"

        current_price = market.current_price

        # Update highest price for trailing stop
        if self.highest_price_since_entry is None or current_price > self.highest_price_since_entry:
            self.highest_price_since_entry = current_price

        # Calculate profit/loss
        pnl_pct = (current_price - self.entry_price) / self.entry_price

        # 1. Stop Loss (ATR-based)
        prices = list(self.price_history) + [current_price]
        atr = self._calculate_atr(prices)
        if atr:
            stop_loss_price = self.entry_price - (atr * self.stop_loss_atr_multiplier)
            if current_price <= stop_loss_price:
                return True, portfolio.quantity, f"STOP LOSS triggered at {pnl_pct*100:.2f}%"

        # 2. Trailing Stop
        if self.highest_price_since_entry:
            trailing_stop_price = self.highest_price_since_entry * (1 - self.trailing_stop_pct)
            if current_price <= trailing_stop_price:
                return True, portfolio.quantity, f"TRAILING STOP at {pnl_pct*100:.2f}%"

        # 3. Take Profit Levels (partial exits)
        for i, tp_level in enumerate(self.take_profit_levels):
            if pnl_pct >= tp_level:
                # Sell partial position at each TP level
                sell_pct = 0.33  # Sell 33% at each level
                size = portfolio.quantity * sell_pct
                return True, size, f"TAKE PROFIT {i+1} at {pnl_pct*100:.2f}%"

        # 4. Technical exit signals
        rsi = self._calculate_rsi(prices, self.rsi_period)
        if rsi and rsi > self.rsi_overbought:
            # Overbought - consider partial exit
            if pnl_pct > 0.02:  # At least 2% profit
                return True, portfolio.quantity * 0.5, f"RSI overbought exit at {pnl_pct*100:.2f}%"

        # 5. Trend reversal
        ema_fast = self._calculate_ema(prices, self.ema_fast)
        ema_medium = self._calculate_ema(prices, self.ema_medium)
        if ema_fast and ema_medium and ema_fast < ema_medium:
            # Bearish crossover
            if pnl_pct > -0.05:  # Not more than 5% loss
                return True, portfolio.quantity, f"Trend reversal exit at {pnl_pct*100:.2f}%"

        return False, 0.0, "Hold position"

    # ==================== MAIN STRATEGY METHOD ====================

    def generate_signal(self, market: MarketSnapshot, portfolio: Portfolio) -> Signal:
        """Main strategy logic - generate buy/sell/hold signals."""

        # Update price history
        self.price_history.append(market.current_price)

        # Initialize starting portfolio value
        if self.starting_portfolio_value is None:
            self.starting_portfolio_value = portfolio.value(market.current_price)

        # Check for sell signals first
        should_sell, sell_size, sell_reason = self._should_sell(market, portfolio)
        if should_sell:
            self._logger.info(f"SELL signal: {sell_reason}")
            return Signal(
                action="sell",
                size=sell_size,
                reason=sell_reason,
                entry_price=self.entry_price
            )

        # Check for buy signals
        should_buy, position_pct, buy_reason = self._should_buy(market, portfolio)
        if should_buy:
            # Calculate position size
            current_value = portfolio.value(market.current_price)
            position_value = current_value * position_pct
            position_value = min(position_value, portfolio.cash)  # Don't exceed available cash

            if position_value > 0:
                size = position_value / market.current_price
                self._logger.info(f"BUY signal: {buy_reason}")
                return Signal(
                    action="buy",
                    size=size,
                    reason=buy_reason,
                    target_price=market.current_price * 1.10,  # 10% target
                    stop_loss=market.current_price * 0.95  # 5% stop
                )

        # Default: hold
        return Signal("hold", reason="No trading conditions met")

    def on_trade(self, signal: Signal, execution_price: float, execution_size: float, timestamp: datetime) -> None:
        """Update strategy state after trade execution."""
        if signal.action == "buy" and execution_size > 0:
            # Update last trade time for cooldown
            self.last_trade_time = timestamp if timestamp else datetime.now(timezone.utc)

            # Calculate new average entry price
            if self.entry_price and self.current_quantity > 0:
                total_value = (self.entry_price * self.current_quantity) + (execution_price * execution_size)
                total_quantity = self.current_quantity + execution_size
                self.entry_price = total_value / total_quantity
            else:
                self.entry_price = execution_price

            self.highest_price_since_entry = execution_price
            self.current_quantity += execution_size

            self.positions.append({
                "price": execution_price,
                "size": execution_size,
                "timestamp": timestamp.isoformat() if timestamp else datetime.now(timezone.utc).isoformat()
            })

            self._logger.info(f"BUY executed: {execution_size:.8f} @ ${execution_price:,.2f}")

        elif signal.action == "sell" and execution_size > 0:
            # Update quantity
            self.current_quantity -= execution_size

            # Remove sold positions (FIFO)
            remaining = execution_size
            while self.positions and remaining > 0:
                position = self.positions[0]
                if position["size"] <= remaining:
                    remaining -= position["size"]
                    self.positions.popleft()
                else:
                    position["size"] -= remaining
                    remaining = 0

            # If sold entire position, reset entry tracking
            if len(self.positions) == 0:
                self.entry_price = None
                self.highest_price_since_entry = None
                self.current_quantity = 0.0  # Reset to zero

            pnl = (execution_price - (signal.entry_price or execution_price)) * execution_size
            self._logger.info(f"SELL executed: {execution_size:.8f} @ ${execution_price:,.2f} (PnL: ${pnl:,.2f})")

    def get_state(self) -> Dict[str, Any]:
        """Save strategy state for persistence."""
        return {
            "positions": list(self.positions),
            "entry_price": self.entry_price,
            "highest_price_since_entry": self.highest_price_since_entry,
            "starting_portfolio_value": self.starting_portfolio_value,
            "current_quantity": self.current_quantity,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "price_history": list(self.price_history)
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        """Restore strategy state."""
        self.positions = deque(state.get("positions", []))
        self.entry_price = state.get("entry_price")
        self.highest_price_since_entry = state.get("highest_price_since_entry")
        self.starting_portfolio_value = state.get("starting_portfolio_value")
        self.current_quantity = state.get("current_quantity", 0.0)

        # Restore last trade time
        last_trade_str = state.get("last_trade_time")
        if last_trade_str:
            self.last_trade_time = datetime.fromisoformat(last_trade_str)

        if "price_history" in state:
            self.price_history = deque(state["price_history"], maxlen=self.price_history.maxlen)


# Register the strategy
register_strategy("quantum_momentum_pro", lambda cfg, ex: QuantumMomentumProStrategy(cfg, ex))
