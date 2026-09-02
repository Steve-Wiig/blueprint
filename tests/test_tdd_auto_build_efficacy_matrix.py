import pytest
from build_efficacy_matrix import build_efficacy_matrix


def test_sorting_events_per_remediation_id_uses_global_sort():
    events = [
        {"remediation_id": "B", "timestamp": 2, "value": "b2"},
        {"remediation_id": "A", "timestamp": 1, "value": "a1"},
        {"remediation_id": "B", "timestamp": 1, "value": "b1"},
        {"remediation_id": "A", "timestamp": 2, "value": "a2"},
        {"remediation_id": "C", "timestamp": 1, "value": "c1"},
    ] * 1000

    result = build_efficacy_matrix(events)

    assert "A" in result
    assert "B" in result
    assert "C" in result
    assert all(result[rid][i]["timestamp"] <= result[rid][i + 1]["timestamp"]
               for rid in result for i in range(len(result[rid]) - 1))