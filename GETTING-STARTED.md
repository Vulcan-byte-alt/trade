# Getting Started - Trading Strategy Contest

Complete guide to building and submitting your trading strategy.

## 🏆 Contest Overview
- **Prize Pool**: $1,500 USD (1st: $1,000, 2nd: $300, 3rd: $200)
- **Target**: Build the most profitable BTC/ETH trading strategy
- **Data**: Jan-Jun 2024 backtest period, $10,000 starting capital


## 🚀 Quick Start

### 1. Clone this repository:
```bash
git clone https://github.com/msolomos/strategy-contest.git
cd strategy-contest
```

### 2. Study the infrastructure:
- Review `base-bot-template/` to understand the framework
- Examine `dca-bot-template/` to see implementation patterns

### 3. Create your strategy:
- Copy `dca-bot-template/` as starting point
- Implement your trading logic in the strategy file
- Test locally using the provided tools

## 📋 Submission Requirements

### Required Structure:
```
your-strategy-template/
├─ your_strategy.py      # Main strategy logic
├─ startup.py            # Bot entry point
├─ Dockerfile            # Container definition
├─ requirements.txt      # Dependencies
└─ README.md            # Documentation

reports/
├─ backtest_runner.py    # Verification script
└─ backtest_report.md    # Performance analysis

trade_logic_explanation.md  # Strategy explanation
```

### 4. Submit your strategy:
When ready, include your GitHub repo link in your submission message.

⚠️ **Anything else will cause disqualification.**

## 🎯 Success Requirements

### Contest Rules:
- **Maximum drawdown**: <50% (exceeding this = disqualification)
- **Minimum trades**: At least 10 trades over 6-month period
- **Starting capital**: $10,000 (identical for all participants)
- **Data period**: Jan-Jun 2024 BTC-USD and ETH-USD
- **Platform compatibility**: Must use only price data (no volume)

## ⚖️ Verification Process

All submissions undergo:
1. **Security audit**: Code safety, no malicious patterns
2. **Platform compliance**: BaseStrategy inheritance, proper signals
3. **Performance verification**: Independent backtest confirmation
4. **Risk assessment**: Drawdown limits, trade frequency
5. **Docker verification**: Live container testing

## 📝 Important Contest Rules

### Technical Requirements:
1. **Data Interval**: Must use **hourly data** (interval='1h') for fair comparison
2. **Maximum Position Size**: **55% maximum exposure** per trade (position sizing cannot exceed 0.55 of portfolio)
3. **Data Source**: Yahoo Finance only (yfinance library) - no synthetic or external data
4. **Data Period**: Exactly 2024-01-01 to 2024-06-30 (4344 hourly candles)

### Submission Limits & Policies:
1. **3 Strategy Maximum**: Each participant can submit up to 3 different strategies
2. **No Rejected Strategy Improvements**: Once a strategy is rejected, it cannot be resubmitted or modified
3. **Accepted Strategy Updates**: Strategies that pass evaluation can be continuously improved until contest ends
4. **Zero Tolerance Fraud Policy**: Data manipulation or fraud (AI-assisted or otherwise) results in permanent ban

## 💡 Pro Tips

- **Test thoroughly**: Include comprehensive backtest framework
- **Document clearly**: Explain your trading logic and parameters
- **Keep it simple**: Focus on robust, verifiable strategies
- **Choose wisely**: You only get 3 submissions maximum - make them count
- **Study the framework**: Understand BaseStrategy inheritance requirements

## 🚨 Common Disqualification Reasons

- **Missing files**: Incomplete submission structure
- **Platform incompatibility**: Using unavailable data sources
- **Wrong data interval**: Using daily instead of required hourly data
- **Excessive position sizing**: >55% max exposure limit exceeded
- **Excessive risk**: >50% drawdown limit exceeded
- **Data manipulation**: Using wrong date range or non-Yahoo Finance data
- **Verification failure**: Claims not independently reproducible
- **Security issues**: Malicious code or unsafe dependencies

---

**Ready to build your strategy? Study the framework, implement your logic, and compete for the $1,500 prize pool! 🚀**

