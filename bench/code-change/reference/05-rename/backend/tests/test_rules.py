"""Tests for the refund rules."""
from refunds.rules import requires_sign_off


def test_small_refund_needs_no_approval():
    assert not requires_sign_off(10)


def test_large_refund_needs_approval():
    assert requires_sign_off(1000)
