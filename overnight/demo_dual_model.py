#!/usr/bin/env python3
"""
Demonstration of dual-model cross-validation pipeline.
Shows how Nemotron generates and Gemini critiques for higher quality output.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from overnight.llm_client import generate_with_critique, load_api_keys, strip_fences

def main():
    api_keys = load_api_keys()
    
    if not api_keys["openrouter"]:
        print("ERROR: OPENROUTER_API_KEY not set in .env")
        sys.exit(1)
    if not api_keys["gemini"]:
        print("ERROR: GEMINI_API_KEY not set in .env")
        sys.exit(1)
    
    print("=" * 70)
    print("DUAL-MODEL CROSS-VALIDATION DEMO")
    print("=" * 70)
    
    # Example: Generate a pytest test for a real module
    task = """Generate pytest unit tests for engine/queue_manager.py.
    
Requirements:
- Test the TriageQueueManager class
- Use real sqlite3.connect(":memory:") not mocks
- Test enqueue, claim, complete, and backpressure shedding
- Expect RuntimeError not SystemExit
- Output ONLY Python code, no markdown"""
    
    print(f"\nTask: Generate tests for queue_manager.py")
    print(f"\n{'='*70}")
    print("STEP 1: Nemotron generates initial code")
    print("=" * 70)
    
    from overnight.llm_client import generate
    initial = generate(task, api_keys, model_type="code")
    initial = strip_fences(initial)
    
    print(f"\nGenerated {len(initial.splitlines())} lines")
    print(f"Preview (first 300 chars):\n{initial[:300]}...")
    
    print(f"\n{'='*70}")
    print("STEP 2: Gemini critiques the output")
    print("=" * 70)
    
    from overnight.llm_client import critique
    is_good, critique_text = critique(initial, "pytest tests for TriageQueueManager", api_keys)
    
    print(f"\nVerdict: {'APPROVE' if is_good else 'REVISE'}")
    print(f"Critique:\n{critique_text[:500]}...")
    
    print(f"\n{'='*70}")
    print("STEP 3: Full generate-with-critique loop")
    print("=" * 70)
    
    final = generate_with_critique(task, "pytest tests for TriageQueueManager", 
                                    api_keys, model_type="code", max_iterations=2)
    final = strip_fences(final)
    
    print(f"\n✅ Final output: {len(final.splitlines())} lines")
    print(f"\nFinal code (first 500 chars):\n{final[:500]}")
    
    # Quick syntax check
    try:
        compile(final, "<test>", "exec")
        print("\n✅ Generated code is syntactically valid Python")
    except SyntaxError as e:
        print(f"\n⚠️  Syntax issue: {e}")

if __name__ == "__main__":
    main()
