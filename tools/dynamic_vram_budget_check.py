#!/usr/bin/env python3
# CI Gate: Dynamic VRAM Budget Check
import os
import sys
import subprocess
import xml.etree.ElementTree as ET
import re

def get_gpu_info():
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

def parse_mem_value(val_str):
    """Extracts integer value from strings like '16384 MiB'."""
    match = re.search(r'(\d+)', val_str)
    return int(match.group(1)) if match else 0

def main():
    gpu_data = get_gpu_info()
    if gpu_data is None:
        print("FAIL: GPU unavailable or nvidia-smi failed")
        return 1

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
                print("CONFIG ERROR: VRAM_BUDGET_MB must be a positive integer")
                return 2
        else:
            budget_mb = int(total_mb * 0.9)

    except (AttributeError, ValueError, TypeError):
        print("CONFIG ERROR: Failed to parse or validate GPU memory metrics")
        return 2

    if used_mb > budget_mb:
        print(f"FAIL: VRAM usage {used_mb}MB exceeds budget {budget_mb}MB")
        return 1

    print(f"PASS: VRAM usage {used_mb}MB within budget {budget_mb}MB")
    return 0

if __name__ == "__main__":
    sys.exit(main())