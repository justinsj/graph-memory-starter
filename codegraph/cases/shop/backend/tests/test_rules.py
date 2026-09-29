"""Tests for the refund rules."""
from refunds.rules import needs_approval


def test_small_refund_needs_no_approval():
    assert not needs_approval(10)


def test_large_refund_needs_approval():
    assert needs_approval(1000)
