#!/usr/bin/env python3
"""Test MatchStatus enum values."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.domain.enums import MatchStatus

def test_enum():
    print('MatchStatus.FINISHED value:', repr(MatchStatus.FINISHED))
    print('MatchStatus.FINISHED == "FINISHED":', MatchStatus.FINISHED == 'FINISHED')
    print('MatchStatus.FINISHED == "finished":', MatchStatus.FINISHED == 'finished')
    print('MatchStatus.SCHEDULED value:', repr(MatchStatus.SCHEDULED))

if __name__ == "__main__":
    test_enum()
