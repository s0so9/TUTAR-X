#!/usr/bin/env python3
"""Extract diagnostic lines from profiler output."""

import sys

try:
    with open('profile_output_diagnostic.txt', 'r', encoding='utf-16-le') as f:
        for i, line in enumerate(f):
            if any(marker in line for marker in ['[SETUP]', '[ERROR]', '[RESULT]', '[ELO]', '[DEBUG]', '[PROFILE]', 'match_id', 'Testing with match', 'Traceback', 'Error', 'Exception']):
                print(line.rstrip())
            if i > 5000:  # Safety limit
                break
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
