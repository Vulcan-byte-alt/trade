#!/usr/bin/env python3
"""Startup script for Simple Trend Strategy Bot."""

import sys
import os

# Add base-bot-template to path
base_path = os.path.join(os.path.dirname(__file__), '..', 'base-bot-template')
if not os.path.exists(base_path):
    base_path = '/app/base'

sys.path.insert(0, base_path)

# Import and register the ASYMMETRIC strategy (BTC trend rider + ETH dip buyer)
import asymmetric_strategy

# Import and start the universal bot
from universal_bot import UniversalBot

if __name__ == "__main__":
    bot = UniversalBot()
    bot.run()
