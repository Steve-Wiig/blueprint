import pytest
from sanitization_field_policy_check import find_forbidden


def test_find_forbidden_deep_nesting_performance():
    schema = {"type": "object", "properties": {}}
    current = schema["properties"]
    depth = 1000
    for i in range(depth):
        current[f"level_{i}"] = {"type": "object", "properties": {}}
        current = current[f"level_{i}"]["properties"]
    current["secret"] = {"type": "string", "forbidden": True}

    result = find_forbidden(schema)

    assert "level_0.level_1.level_2.level_3.level_4.level_5.level_6.level_7.level_8.level_9.secret" in result
    assert len(result) == 1