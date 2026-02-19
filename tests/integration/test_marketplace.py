"""Integration tests for marketplace endpoints (read-only)."""

import pytest

pytestmark = pytest.mark.integration


class TestMarketplaceFee:
    def test_get_fee(self, client):
        fee = client.marketplace.fee.get(price=10.00)
        assert isinstance(fee.value, float)
        assert fee.value > 0

    def test_get_fee_with_currency(self, client):
        fee = client.marketplace.fee.get(price=10.00, currency="USD")
        assert isinstance(fee.value, float)
        assert fee.currency == "USD"
