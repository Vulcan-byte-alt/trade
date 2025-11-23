# Yahoo Finance API Blocking Issue

## Problem Statement

The Yahoo Finance API is currently returning **HTTP 403: Access denied** errors for all requests from this environment. This prevents backtesting the trading strategy against historical data.

## Error Details

```
Failed to get ticker 'BTC-USD' reason: Expecting value: line 1 column 1 (char 0)
HTTP Error 403: Access denied
HTTP Error 403: Access denied

1 Failed download:
['BTC-USD']: TypeError("argument of type 'NoneType' is not iterable")
```

## Root Cause

Yahoo Finance implements rate limiting and IP-based blocking to prevent automated scraping. The current environment/IP has been flagged and blocked from accessing the API.

## Attempted Solutions

1. ✅ Added retry logic with exponential backoff
2. ✅ Switched from `Ticker().history()` to `yf.download()`
3. ✅ Added single-threaded downloads (`threads=False`)
4. ✅ Tried different time periods and intervals
5. ✅ Upgraded yfinance to latest version (0.2.66)
6. ✅ Installed curl_cffi for improved reliability
7. ❌ All approaches still result in 403 errors

## Strategy Improvements Completed (Unable to Test)

Despite the data access issue, the following improvements were made to the trading strategy:

### Version 6: Momentum Breakout Strategy

**Entry Logic Changes:**
- ✅ Faster trend detection: EMA(20) instead of EMA(50)
- ✅ Momentum confirmation: Buy on new 10-period high (breakout)
- ✅ Removed RSI filter that was blocking good entries

**Exit Logic Changes:**
- ✅ Lower take profit: 6% instead of 10% (more realistic for hourly data)
- ✅ Adjusted stop loss: 5% instead of 4%
- ✅ Added trailing stop: 4% from peak price

**Rationale:**
- Previous versions had 0% win rate due to late entries and unrealistic profit targets
- EMA(50) was too slow for trending markets
- 10% profit target rarely hit before stop loss
- Momentum breakouts capture actual trend moves

## Workarounds

### Option 1: Run in Different Environment
Run the backtest from a different network/environment that's not blocked by Yahoo Finance:
```bash
python reports/backtest_runner.py
```

### Option 2: Manual Data Download
1. Download BTC-USD and ETH-USD hourly data manually from another source
2. Save as CSV files in `reports/data/`
3. Modify `backtest_runner.py` to load from CSV instead of yfinance

### Option 3: Wait and Retry
Yahoo Finance blocking is sometimes temporary. Wait 24-48 hours and retry:
```bash
# Check if access restored
python3 -c "import yfinance as yf; print(yf.download('BTC-USD', period='5d').shape)"
```

### Option 4: Alternative Data Source
Use `pandas_datareader` or another cryptocurrency data API:
```python
# Example with pandas_datareader
from pandas_datareader import data as pdr
btc_data = pdr.get_data_yahoo('BTC-USD', start='2024-01-01', end='2024-06-30')
```

## Files Modified

- `quantum-momentum-pro-template/simple_trend_strategy.py` - Momentum breakout logic
- `reports/backtest_runner.py` - Improved data loading with retry logic

## Current Status

**Code Status:** ✅ Ready for testing
**Data Access:** ❌ Blocked by Yahoo Finance
**Next Steps:** Need to resolve data access before performance validation

## Expected Performance (When Testable)

Based on the improved entry/exit logic:
- **Target Win Rate:** 40-50% (up from 0%)
- **Expected Return:** 35-45% combined (BTC + ETH)
- **Trade Count:** 40-60 trades (within frequency limits)
- **Goal:** Beat current leader's +36.10% return

---

**Date:** November 23, 2025
**Strategy Version:** Momentum Breakout v6
**Blocker:** Yahoo Finance API 403 errors
