import pytest
from engine.cer_critic import generate_strategic_constraint

def test_critic_returns_string():
    constraint = generate_strategic_constraint("def foo(): return 1/0", "ZeroDivisionError", "Fix the division")
    assert isinstance(constraint, str)
    assert "CRITICAL STRATEGY SHIFT" in constraint
    assert len(constraint) < 400
