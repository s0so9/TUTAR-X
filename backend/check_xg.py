#!/usr/bin/env python3
with open('profile_output_diagnostic.txt', 'r', encoding='utf-16-le') as f:
    for line in f:
        if any(x in line for x in ['Strength metrics', 'Expected goals', 'Cannot calculate expected']):
            print(line.rstrip())
