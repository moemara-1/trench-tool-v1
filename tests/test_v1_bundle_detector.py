from datetime import datetime

import pytest

from models import TradeAction
from services.bundle_detector import BundleDetector


def test_bundle_detector_flags_adjacent_block_coordinated_buys():
    detector = BundleDetector()
    token = "TokenMint111111111111111111111111111111111111"

    for index, block_number in enumerate((100, 101, 102)):
        bundle = detector.add_transaction(
            token_address=token,
            wallet_address=f"wallet_{index}",
            amount_sol=0.7,
            token_amount=1000,
            action=TradeAction.BUY,
            timestamp=datetime.utcnow(),
            block_number=block_number,
        )

    assert bundle is not None
    assert bundle.wallet_count == 3
    assert bundle.total_volume_sol == pytest.approx(2.1)
    assert bundle.action == "buy"
