#!/usr/bin/env python3
"""
Send a large text corpus to a high-context LLM via OpenRouter for analysis.
Designed for failure-pattern analysis, documentation audits, and code reviews
that exceed local VRAM context limits.

Usage:
    python3 tools/llm_analyze.py <input_file.txt>
    python3 tools/llm_analyze.py post_run_analysis.txt
    python3 tools/llm_analyze.py audit_context.txt --model anthropic/claude-3.5-sonnet
    python3 tools/llm_analyze.py data.txt --prompt-file custom_prompt.txt
"""
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    print("⚠️  python-dotenv not installed. Falling back to environment variables.")
    print("   Install with: pip install python-dotenv")

from openai import OpenAI

# Default prompt for failure-pattern analysis (the most common use case)
DEFAULT_PROMPT = """You are a Staff Software Engineer and Security Architect reviewing the overnight run of an autonomous AI coding agent.

The agent attempted to fix issues in a local SOC/SIEM pipeline. Some succeeded, some were rejected by safety gates (AST, Pytest, Truncation), and some were deferred for human review.

### YOUR TASK:
Perform a "Failure Pattern Analysis" on the rejections and deferred items in the data below.

1. **Categorize the Failures:** Group the rejections into 3-5 distinct categories (e.g., "AI struggles with multi-line SQL", "AI breaks test mocks when changing signatures", "AI hallucinates missing imports"). Provide estimated counts for each.
2. **Identify Architectural Debt:** Based on the deferred items and repeated failures, what underlying technical debt or design patterns in this codebase are making it hostile to AI refactoring? (e.g., tight coupling, global state, complex test fixtures, hardcoded SQL timestamps).
3. **Recommend 3 "Pre-Refactoring" Tasks:** Before I let the AI loose again, what 3 manual architectural changes should I make to the codebase to increase the AI's success rate from ~45% to 80%?

Output a structured, executive-level report. Be ruthless and analytical. Do not suggest the AI just "try harder." Tell me what I need to fix in the codebase architecture to make it AI-friendly.

=== BEGIN DATA ===
{corpus}
=== END DATA ===
"""


def main():
    parser = argparse.ArgumentParser(
        description="Send a large text file to a high-context LLM via OpenRouter for analysis."
    )
    parser.add_argument("input_file", help="Path to the text file to analyze")
    parser.add_argument(
        "--model",
        default="qwen/qwen-2.5-72b-instruct",
        help="OpenRouter model ID (default: qwen/qwen-2.5-72b-instruct)"
    )
    parser.add_argument(
        "--prompt-file",
        help="Optional: path to a custom prompt file. Use {corpus} as placeholder for the input data."
    )
    parser.add_argument(
        "--output",
        help="Optional: explicit output file path (default: auto-generated timestamp)"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4000,
        help="Max tokens for the response (default: 4000)"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Temperature for the response (default: 0.2)"
    )
    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    # Validate API key
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in .env or environment.")
        print("   Add it to your project's .env file:")
        print("   OPENROUTER_API_KEY=sk-or-v1-...")
        sys.exit(1)

    # Read input file
    print(f"📖 Reading {input_path}...")
    corpus = input_path.read_text(encoding="utf-8")
    print(f"   Loaded {len(corpus):,} characters ({len(corpus.split()):,} words)")

    # Build prompt
    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            print(f"❌ Prompt file not found: {prompt_path}")
            sys.exit(1)
        prompt_template = prompt_path.read_text(encoding="utf-8")
        if "{corpus}" not in prompt_template:
            print("⚠️  Warning: Prompt file doesn't contain {corpus} placeholder. Appending data.")
            prompt_template += "\n\n=== BEGIN DATA ===\n{corpus}\n=== END DATA ==="
    else:
        prompt_template = DEFAULT_PROMPT

    user_prompt = prompt_template.replace("{corpus}", corpus)

    # Initialize client
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    print(f"\n🚀 Sending to OpenRouter model: {args.model}")
    print(f"   Max tokens: {args.max_tokens} | Temperature: {args.temperature}")
    print("   (This may take 30-90 seconds for large files...)\n")

    try:
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "You are a Staff Software Engineer and Security Architect. Provide structured, evidence-based analysis."},
                {"role": "user", "content": user_prompt}
            ],
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
    except Exception as e:
        print(f"❌ API request failed: {e}")
        sys.exit(1)

    result = response.choices[0].message.content

    # Display result
    print("\n" + "=" * 70)
    print(f"📊 ANALYSIS REPORT ({args.model})")
    print("=" * 70 + "\n")
    print(result)

    # Save to file
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"overnight/llm_analysis_{timestamp}.md")

    output_path.write_text(result, encoding="utf-8")
    print(f"\n✅ Report saved to: {output_path}")

    # Print usage stats if available
    if hasattr(response, "usage") and response.usage:
        print(f"\n📈 Token usage:")
        print(f"   Prompt:     {response.usage.prompt_tokens:,}")
        print(f"   Completion: {response.usage.completion_tokens:,}")
        print(f"   Total:      {response.usage.total_tokens:,}")


if __name__ == "__main__":
    main()
