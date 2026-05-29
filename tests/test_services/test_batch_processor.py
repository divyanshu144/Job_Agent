from __future__ import annotations


def test_discovery_batch_model_importable():
    from backend.models import DiscoveryBatch

    assert hasattr(DiscoveryBatch, "anthropic_batch_id")
    assert hasattr(DiscoveryBatch, "run_id")
    assert hasattr(DiscoveryBatch, "status")
    assert hasattr(DiscoveryBatch, "request_count")
    assert hasattr(DiscoveryBatch, "submitted_at")
    assert hasattr(DiscoveryBatch, "completed_at")
