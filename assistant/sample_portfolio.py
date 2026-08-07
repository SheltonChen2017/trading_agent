"""
EXAMPLE portfolio for demoing the assistant package — NOT the user's real
holdings. Edit SAMPLE_POSITIONS/SAMPLE_CASH directly, or write your own
equivalent list of dicts, until a live broker connection replaces this
(see context_builder.py's module docstring).
"""

SAMPLE_POSITIONS = [
    {"ticker": "NVDA", "shares": 20, "entry_price": 120.0, "current_price": 175.0},
    {"ticker": "AMD", "shares": 40, "entry_price": 150.0, "current_price": 160.0},
    {"ticker": "SOXX", "shares": 30, "entry_price": 220.0, "current_price": 240.0},
    {"ticker": "SOXL", "shares": 15, "entry_price": 40.0, "current_price": 55.0},
    {"ticker": "QQQ", "shares": 10, "entry_price": 480.0, "current_price": 510.0},
]
SAMPLE_CASH = 5_000.0
