"""Tests for options_signals utility functions."""

from openbb_ibkr.utils.options_signals import realized_vol_from_bars


def test_realized_vol_from_bars_empty():
    """Returns None for empty bars."""
    assert realized_vol_from_bars([]) is None


def test_realized_vol_from_bars_insufficient():
    """Returns a value even with fewer bars than window (uses available data)."""
    bars = [{"close": 100 + i} for i in range(10)]
    result = realized_vol_from_bars(bars, window=63)
    # Function computes with available data rather than returning None
    assert result is not None
    assert result >= 0


def test_realized_vol_from_bars_valid():
    """Returns a positive float for sufficient data."""
    import random
    random.seed(42)
    bars = [{"close": 100 + random.gauss(0, 2)} for _ in range(100)]
    result = realized_vol_from_bars(bars, window=63)
    assert result is not None
    assert result > 0
    assert result < 2.0  # Annualized vol should be reasonable
