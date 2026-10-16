"""Small Turkish text helpers for the fixed highlight templates."""

from __future__ import annotations

from typing import Sequence

# Accusative with possessive suffix of the numerals that can appear as "N of the last 5 matches".
_NUMBER_ACCUSATIVE = {0: "0'ı", 1: "1'ini", 2: "2'sini", 3: "3'ünü", 4: "4'ünü", 5: "5'ini"}


def count_accusative(n: int) -> str:
    """'3' -> "3'ünü" (for "son 5 maçın 3'ünü kaybetti"); only 0..5 are used by the templates."""
    if n not in _NUMBER_ACCUSATIVE:
        raise ValueError(f"no suffix table entry for {n}")
    return _NUMBER_ACCUSATIVE[n]


def decimal(value: float, digits: int = 1) -> str:
    """Turkish decimal comma: 5.84 -> '5,8'."""
    return f"{value:.{digits}f}".replace(".", ",")


def join_names(names: Sequence[str]) -> str:
    """['A', 'B', 'C'] -> 'A, B ve C'."""
    items = [n for n in names if n]
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} ve {items[-1]}"
