#!/usr/bin/env python3
"""Backtest runner for Trading Strategy Contest.

This script backtests strategies on historical data from Yahoo Finance.
Contest Requirements:
- Data source: Yahoo Finance (yfinance library)
- Data interval: 1 hour (1h)
- Period: 2024-01-01 to 2024-06-30
- Starting capital: $10,000
- Symbols: BTC-USD, ETH-USD
"""

import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Any
import json

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'base-bot-template'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'quantum-momentum-pro-template'))

# Import yfinance for data
try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

# Import strategy components
from strategy_interface import Portfolio, Signal
from exchange_interface import MarketSnapshot
from simple_trend_strategy import SimpleTrendStrategy


class BacktestEngine:
    """Simple backtest engine for contest verification."""

    def __init__(self, symbol: str, start_date: str, end_date: str, starting_cash: float = 10000.0):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.starting_cash = starting_cash

        # Portfolio state
        self.cash = starting_cash
        self.quantity = 0.0

        # Performance tracking
        self.trades: List[Dict[str, Any]] = []
        self.portfolio_values: List[float] = []
        self.timestamps: List[datetime] = []

        # Load data
        print(f"\n📊 Loading {symbol} data from Yahoo Finance...")
        print(f"   Period: {start_date} to {end_date}")
        print(f"   Interval: 1 hour")

        # Try multiple times with retry logic
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use download() which is more reliable than Ticker().history()
                self.data = yf.download(
                    symbol,
                    start=start_date,
                    end=end_date,
                    interval="1h",
                    progress=False,
                    threads=False  # Avoid multitasking module issues
                )

                if self.data is not None and not self.data.empty:
                    print(f"   ✅ Loaded {len(self.data)} hourly candles")
                    break
                elif attempt < max_retries - 1:
                    print(f"   ⚠️  No data received, retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(3)
                else:
                    raise ValueError(f"No data received for {symbol} after {max_retries} attempts")
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ⚠️  Error: {e}, retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(3)
                else:
                    raise ValueError(f"Failed to load data for {symbol}: {e}")

    def run(self, strategy_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run backtest with given strategy configuration."""
        print(f"\n🚀 Starting backtest for {self.symbol}...")

        # Create strategy instance
        # Exchange is not needed for backtesting
        class DummyExchange:
            pass

        strategy = SimpleTrendStrategy(config=strategy_config, exchange=DummyExchange())

        # Initialize portfolio
        portfolio = Portfolio(
            symbol=self.symbol,
            cash=self.cash,
            quantity=self.quantity
        )

        # Iterate through each candle
        for i, (timestamp, row) in enumerate(self.data.iterrows()):
            current_price = float(row['Close'])

            # Build price history
            prices = self.data['Close'].iloc[:i+1].tolist()

            # Create market snapshot
            market = MarketSnapshot(
                symbol=self.symbol,
                current_price=current_price,
                prices=prices,
                timestamp=timestamp
            )

            # Update portfolio
            portfolio.cash = self.cash
            portfolio.quantity = self.quantity

            # Generate signal
            signal = strategy.generate_signal(market, portfolio)

            # Execute signal
            if signal.action == "buy" and signal.size > 0:
                # Calculate maximum affordable size
                max_size = self.cash / current_price
                actual_size = min(signal.size, max_size)

                if actual_size > 0:
                    cost = actual_size * current_price
                    self.cash -= cost
                    self.quantity += actual_size

                    trade = {
                        "timestamp": timestamp.isoformat(),
                        "side": "buy",
                        "price": current_price,
                        "size": actual_size,
                        "cost": cost,
                        "reason": signal.reason
                    }
                    self.trades.append(trade)

                    # Notify strategy
                    strategy.on_trade(signal, current_price, actual_size, timestamp)

                    print(f"   BUY  {actual_size:.8f} @ ${current_price:,.2f} | Cash: ${self.cash:,.2f}")

            elif signal.action == "sell" and signal.size > 0:
                # Sell up to available quantity
                actual_size = min(signal.size, self.quantity)

                if actual_size > 0:
                    proceeds = actual_size * current_price
                    self.cash += proceeds
                    self.quantity -= actual_size

                    # Find matching buy for P&L calculation
                    avg_buy_price = self._calculate_avg_buy_price()
                    pnl = (current_price - avg_buy_price) * actual_size if avg_buy_price else 0

                    trade = {
                        "timestamp": timestamp.isoformat(),
                        "side": "sell",
                        "price": current_price,
                        "size": actual_size,
                        "proceeds": proceeds,
                        "pnl": pnl,
                        "reason": signal.reason
                    }
                    self.trades.append(trade)

                    # Notify strategy
                    strategy.on_trade(signal, current_price, actual_size, timestamp)

                    print(f"   SELL {actual_size:.8f} @ ${current_price:,.2f} | Cash: ${self.cash:,.2f} | PnL: ${pnl:,.2f}")

            # Track portfolio value
            portfolio_value = self.cash + (self.quantity * current_price)
            self.portfolio_values.append(portfolio_value)
            self.timestamps.append(timestamp)

        # Calculate final metrics
        final_price = float(self.data['Close'].iloc[-1])
        final_value = self.cash + (self.quantity * final_price)
        total_return = (final_value - self.starting_cash) / self.starting_cash
        total_pnl = final_value - self.starting_cash

        print(f"\n✅ Backtest complete!")
        print(f"   Final value: ${final_value:,.2f}")
        print(f"   Total return: {total_return*100:.2f}%")
        print(f"   Total P&L: ${total_pnl:,.2f}")
        print(f"   Trades: {len(self.trades)}")

        # Calculate metrics
        metrics = self._calculate_metrics(final_value, total_return, total_pnl)

        return metrics

    def _calculate_avg_buy_price(self) -> float:
        """Calculate average buy price from trade history."""
        total_cost = 0.0
        total_size = 0.0

        for trade in self.trades:
            if trade["side"] == "buy":
                total_cost += trade["cost"]
                total_size += trade["size"]
            elif trade["side"] == "sell":
                # FIFO: reduce total size
                total_size -= trade["size"]

        if total_size > 0 and total_cost > 0:
            return total_cost / total_size
        return 0.0

    def _calculate_metrics(self, final_value: float, total_return: float, total_pnl: float) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""

        # Trade statistics
        buy_trades = [t for t in self.trades if t["side"] == "buy"]
        sell_trades = [t for t in self.trades if t["side"] == "sell"]
        total_trades = len(self.trades)

        # Win rate
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades) if sell_trades else 0

        # Max drawdown
        max_drawdown = 0.0
        peak_value = self.starting_cash

        for value in self.portfolio_values:
            if value > peak_value:
                peak_value = value
            drawdown = (peak_value - value) / peak_value
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Sharpe ratio (simplified - assuming risk-free rate = 0)
        if len(self.portfolio_values) > 1:
            returns = []
            for i in range(1, len(self.portfolio_values)):
                ret = (self.portfolio_values[i] - self.portfolio_values[i-1]) / self.portfolio_values[i-1]
                returns.append(ret)

            if returns:
                mean_return = sum(returns) / len(returns)
                std_return = (sum((r - mean_return) ** 2 for r in returns) / len(returns)) ** 0.5
                sharpe_ratio = (mean_return / std_return) * (len(returns) ** 0.5) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        metrics = {
            "symbol": self.symbol,
            "starting_cash": self.starting_cash,
            "final_value": final_value,
            "total_return_pct": total_return * 100,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "buy_trades": len(buy_trades),
            "sell_trades": len(sell_trades),
            "win_rate_pct": win_rate * 100,
            "max_drawdown_pct": max_drawdown * 100,
            "sharpe_ratio": sharpe_ratio,
            "trades": self.trades
        }

        return metrics


def run_contest_backtest():
    """Run official contest backtest on BTC-USD and ETH-USD."""

    print("=" * 80)
    print("🏆 TRADING STRATEGY CONTEST - BACKTEST RUNNER")
    print("=" * 80)
    print("\nContest Parameters:")
    print("  • Data Source: Yahoo Finance (yfinance)")
    print("  • Interval: 1 hour")
    print("  • Period: 2024-01-01 to 2024-06-30")
    print("  • Starting Capital: $10,000 per symbol")
    print("  • Symbols: BTC-USD, ETH-USD")
    print("=" * 80)

    # MOMENTUM BREAKOUT STRATEGY - Buy Strength, Ride the Wave
    strategy_config = {
        # Faster trend detection
        "trend_ema_period": 20,  # EMA(20) catches trends earlier

        # Momentum confirmation
        "momentum_period": 10,  # New 10-period high = breakout

        # Position sizing
        "position_pct": 0.55,  # Always 55% (max allowed)

        # Realistic exit rules
        "take_profit_pct": 0.06,  # 6% profit (achievable!)
        "stop_loss_pct": 0.05,  # 5% stop loss
        "trailing_stop_pct": 0.04,  # 4% trailing from peak

        # Trade frequency
        "max_trades_per_month": 3  # Max 3 per month
    }

    # Contest parameters
    start_date = "2024-01-01"
    end_date = "2024-06-30"
    starting_cash = 10000.0

    results = {}

    # Test BTC-USD
    try:
        btc_engine = BacktestEngine("BTC-USD", start_date, end_date, starting_cash)
        btc_results = btc_engine.run(strategy_config)
        results["BTC-USD"] = btc_results
    except Exception as e:
        print(f"\n❌ BTC-USD backtest failed: {e}")
        results["BTC-USD"] = {"error": str(e)}

    # Test ETH-USD
    try:
        eth_engine = BacktestEngine("ETH-USD", start_date, end_date, starting_cash)
        eth_results = eth_engine.run(strategy_config)
        results["ETH-USD"] = eth_results
    except Exception as e:
        print(f"\n❌ ETH-USD backtest failed: {e}")
        results["ETH-USD"] = {"error": str(e)}

    # Calculate combined results
    print("\n" + "=" * 80)
    print("📊 COMBINED RESULTS")
    print("=" * 80)

    btc_return = results.get("BTC-USD", {}).get("total_return_pct", 0)
    eth_return = results.get("ETH-USD", {}).get("total_return_pct", 0)
    combined_return = (btc_return + eth_return) / 2

    btc_pnl = results.get("BTC-USD", {}).get("total_pnl", 0)
    eth_pnl = results.get("ETH-USD", {}).get("total_pnl", 0)
    combined_pnl = btc_pnl + eth_pnl

    btc_trades = results.get("BTC-USD", {}).get("total_trades", 0)
    eth_trades = results.get("ETH-USD", {}).get("total_trades", 0)
    total_trades = btc_trades + eth_trades

    btc_win_rate = results.get("BTC-USD", {}).get("win_rate_pct", 0)
    eth_win_rate = results.get("ETH-USD", {}).get("win_rate_pct", 0)
    avg_win_rate = (btc_win_rate + eth_win_rate) / 2

    btc_drawdown = results.get("BTC-USD", {}).get("max_drawdown_pct", 0)
    eth_drawdown = results.get("ETH-USD", {}).get("max_drawdown_pct", 0)
    max_drawdown = max(btc_drawdown, eth_drawdown)

    print(f"\n🎯 BTC-USD:  {btc_return:+.2f}% (${btc_pnl:+,.2f})")
    print(f"🎯 ETH-USD:  {eth_return:+.2f}% (${eth_pnl:+,.2f})")
    print(f"\n{'='*80}")
    print(f"🏆 COMBINED: {combined_return:+.2f}% (${combined_pnl:+,.2f})")
    print(f"{'='*80}")
    print(f"\n📈 Total Trades: {total_trades}")
    print(f"📈 Average Win Rate: {avg_win_rate:.1f}%")
    print(f"📉 Max Drawdown: {max_drawdown:.2f}%")

    # Contest status
    current_leader_return = 36.10
    beats_leader = combined_return > current_leader_return

    print(f"\n{'='*80}")
    if beats_leader:
        print(f"✅ RESULT: BEATS CURRENT LEADER! ({combined_return:.2f}% > {current_leader_return}%)")
    else:
        print(f"❌ RESULT: Below leader ({combined_return:.2f}% < {current_leader_return}%)")
    print(f"{'='*80}\n")

    # Save results to JSON
    output_file = os.path.join(os.path.dirname(__file__), "backtest_results.json")
    with open(output_file, 'w') as f:
        json.dump({
            "combined_return_pct": combined_return,
            "combined_pnl": combined_pnl,
            "total_trades": total_trades,
            "avg_win_rate_pct": avg_win_rate,
            "max_drawdown_pct": max_drawdown,
            "btc_results": results.get("BTC-USD", {}),
            "eth_results": results.get("ETH-USD", {}),
            "beats_current_leader": beats_leader
        }, f, indent=2, default=str)

    print(f"💾 Results saved to: {output_file}\n")

    return results


if __name__ == "__main__":
    run_contest_backtest()
