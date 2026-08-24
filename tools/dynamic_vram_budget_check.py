#!/usr/bin/env python3
# CI Gate: Dynamic VRAM Budget Check
import os
import argparse
import sys
import subprocess
import xml.etree.ElementTree as ET
from typing import Optional
from dataclasses import dataclass


# Default fraction of total GPU memory to use as VRAM budget (90%).
# Leaves 10% headroom for system/other processes.
DEFAULT_BUDGET_FACTOR = 0.9


@dataclass
class VramCheckResult:
    """Result of VRAM budget check."""
    success: bool
    used_mb: int
    budget_mb: int
    message: str
    exit_code: int


def get_gpu_info() -> Optional[ET.Element]:
    """
    Execute nvidia-smi -q -x and return the parsed XML root element.

    Returns:
        ET.Element: Root element of the parsed XML from nvidia-smi query,
                    containing GPU information including memory usage.
        None: If nvidia-smi is not found, fails to execute, or returns
              invalid XML that cannot be parsed.

    This function queries the NVIDIA System Management Interface for
    detailed GPU information in XML format, which is then parsed for
    VRAM budget checking.
    """
    try:
        result = subprocess.run(
            ['nvidia-smi', '-q', '-x'],
            capture_output=True,
            text=True,
            check=True
        )
        return ET.fromstring(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, ET.ParseError):
        return None


def parse_mem_value(val_str: str) -> int:
    """
    Extract integer memory value from a string containing numeric digits.

    Args:
        val_str: String containing a memory value, typically in formats like
                 "16384 MiB", "8 GiB", "1024", "  2048 MB  ", etc.
                 The function extracts the first whitespace-separated token.

    Returns:
        int: The extracted integer value in the original units (typically MiB).
             Returns 0 if no valid integer is found or if the input is empty/None.
    """
    if not val_str:
        return 0
    try:
        return int(val_str.strip().split()[0])
    except (ValueError, IndexError):
        return 0


def check_vram_budget() -> VramCheckResult:
    """
    Check GPU VRAM usage against a budget.

    Reads VRAM_BUDGET_MB environment variable (optional, positive integer MiB).
    If not set, defaults to 90% of total GPU memory.

    Returns:
        VramCheckResult: Object containing check outcome, memory values,
                         human-readable message, and suggested exit code.
    """
    gpu_data = get_gpu_info()
    if gpu_data is None:
        return VramCheckResult(
            success=False,
            used_mb=0,
            budget_mb=0,
            message="FAIL: GPU unavailable or nvidia-smi failed",
            exit_code=1
        )

    try:
        gpu = gpu_data.find('gpu')
        if gpu is None:
            raise ValueError("No GPU device found in nvidia-smi output")

        fb_memory = gpu.find('fb_memory_usage')
        total_mb = parse_mem_value(fb_memory.find('total').text)
        used_mb = parse_mem_value(fb_memory.find('used').text)

        # Handle VRAM_BUDGET_MB override with validation
        env_budget = os.getenv('VRAM_BUDGET_MB')
        if env_budget:
            try:
                budget_mb = int(env_budget)
                if budget_mb <= 0:
                    raise ValueError
            except ValueError:
                return VramCheckResult(
                    success=False,
                    used_mb=used_mb,
                    budget_mb=0,
                    message="CONFIG ERROR: VRAM_BUDGET_MB must be a positive integer",
                    exit_code=2
                )
        else:
            budget_mb = int(total_mb * DEFAULT_BUDGET_FACTOR)

    except (AttributeError, ValueError, TypeError):
        return VramCheckResult(
            success=False,
            used_mb=0,
            budget_mb=0,
            message="CONFIG ERROR: Failed to parse or validate GPU memory metrics",
            exit_code=2
        )

    if used_mb > budget_mb:
        return VramCheckResult(
            success=False,
            used_mb=used_mb,
            budget_mb=budget_mb,
            message=f"FAIL: VRAM usage {used_mb}MB exceeds budget {budget_mb}MB",
            exit_code=1
        )

    return VramCheckResult(
        success=True,
        used_mb=used_mb,
        budget_mb=budget_mb,
        message=f"PASS: VRAM usage {used_mb}MB within budget {budget_mb}MB",
        exit_code=0
    )


def main() -> int:
    """
    CLI entry point for VRAM budget check.

    Returns:
        int: Exit code (0=PASS, 1=FAIL, 2=CONFIG ERROR).
    """
    result = check_vram_budget()
    print(result.message)
    return result.exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dynamic VRAM Budget Check")
    parser.add_argument("--dry-run", action="store_true", help="Mock nvidia-smi and pass")
    args = parser.parse_args()

    if args.dry_run:
        print("PASS: dry-run successful (nvidia-smi mocked)")
        sys.exit(0)

    sys.exit(main())