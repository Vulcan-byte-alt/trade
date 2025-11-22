# Quantum Momentum Pro Strategy

## Overview

Quantum Momentum Pro is an advanced multi-indicator trading strategy designed for high-probability entries in trending markets. It combines technical analysis indicators with dynamic risk management to maximize returns while maintaining strict drawdown control.

## Strategy Components

### 1. **Triple EMA System (Trend Direction)**
- Fast EMA (20 periods): Short-term trend
- Medium EMA (50 periods): Intermediate trend
- Slow EMA (100 periods): Long-term trend
- **Logic**: Bullish when Fast > Medium > Slow

### 2. **RSI (Momentum Oscillator)**
- Period: 14
- Oversold: < 35
- Overbought: > 70
- **Logic**: Buy in oversold/neutral, sell in overbought

### 3. **MACD (Trend Confirmation)**
- Fast: 12, Slow: 26, Signal: 9
- **Logic**: Bullish when MACD line > Signal line

### 4. **Bollinger Bands (Volatility-Based Entries)**
- Period: 20
- Standard Deviation: 2.0
- **Logic**: Buy near lower band, sell near upper band

### 5. **ATR (Dynamic Risk Management)**
- Period: 14
- **Logic**: Stop loss = Entry - (2 × ATR)

## Signal Generation

### Buy Signals (All conditions required):
1. **Trend Alignment**: Fast EMA > Medium EMA
2. **Momentum**: RSI < 70 (not overbought)
3. **Signal Strength**: ≥ 50% indicator confluence
4. **Position Limit**: < 70% of portfolio invested
5. **Drawdown Check**: Current drawdown < 35%

### Signal Strength Calculation (0-100%):
- Triple EMA alignment: +16.7%
- RSI position: +16.7%
- MACD bullish: +16.7%
- Bollinger Band position: +16.7%
- Price momentum (10-period): +16.7%
- Low volatility (ATR): +16.7%

### Position Sizing:
- **Minimum**: 30% of portfolio
- **Maximum**: 55% of portfolio
- **Dynamic**: Size = 30% + (Signal Strength × 25%)
- Example: 80% signal strength → 50% position size

### Sell Signals (Any condition triggers):
1. **Stop Loss**: Price ≤ Entry - (2 × ATR)
2. **Trailing Stop**: Price ≤ Highest Price × (1 - 4%)
3. **Take Profit 1**: +5% gain (sell 33%)
4. **Take Profit 2**: +8% gain (sell 33%)
5. **Take Profit 3**: +12% gain (sell 33%)
6. **RSI Overbought**: RSI > 70 AND profit > 2% (sell 50%)
7. **Trend Reversal**: Fast EMA < Medium EMA AND loss < 5% (sell all)

## Risk Management

- **Max Position Size**: 55% per trade (contest requirement)
- **Max Drawdown Protection**: 35% threshold
- **ATR-Based Stop Loss**: 2× ATR below entry
- **Trailing Stop**: 4% from highest price
- **Partial Profit Taking**: 3 levels at 5%, 8%, 12%

## Configuration Parameters

```python
{
    "strategy_type": "quantum_momentum_pro",

    # Moving Averages
    "ema_fast": 20,
    "ema_medium": 50,
    "ema_slow": 100,

    # RSI
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 70,

    # MACD
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,

    # Bollinger Bands
    "bb_period": 20,
    "bb_std": 2.0,

    # ATR
    "atr_period": 14,

    # Position Sizing
    "base_position_pct": 0.45,
    "max_position_pct": 0.55,
    "min_position_pct": 0.30,

    # Risk Management
    "stop_loss_atr_multiplier": 2.0,
    "tp_level_1": 0.05,
    "tp_level_2": 0.08,
    "tp_level_3": 0.12,
    "trailing_stop_pct": 0.04,
    "max_drawdown_pct": 0.35
}
```

## Performance Targets

- **Target Return**: > 36% (beat current leader)
- **Max Drawdown**: < 35%
- **Win Rate**: > 70%
- **Minimum Trades**: ≥ 10 (contest requirement)

## Usage

### Local Development
```bash
python startup.py
```

### Docker
```bash
docker build -t quantum-momentum-pro .
docker run quantum-momentum-pro
```

### Environment Variables
```bash
STRATEGY_TYPE=quantum_momentum_pro
SYMBOL=BTC-USD
STARTING_CASH=10000
SLEEP_SECONDS=60
```

## Backtesting

See `reports/backtest_runner.py` for backtesting on historical data (Jan-Jun 2024).

```bash
python reports/backtest_runner.py
```

## Strategy Philosophy

This strategy is designed for **trending markets** with **moderate volatility**. It excels when:

1. **Clear trends exist**: EMA alignment captures momentum
2. **Volatility is moderate**: Bollinger Bands identify good entry points
3. **Mean reversion occurs**: RSI catches oversold bounces in uptrends

The multi-indicator approach ensures high-quality signals with strong confluence, resulting in a high win rate and controlled drawdowns.

## Author

Developed for the Trading Strategy Contest 2025

## License

Proprietary - Contest Submission
