"""Pre-match analysis ("Maç analizi"): last 5 matches, home/away form, rest days,
absentees and line-up rotation, with deterministic Turkish highlights.

Public entry points: ``get_match_preview_service()`` and the pure helpers in
``history``, ``rotation`` and ``highlights``. No AI text generation: every sentence
is a fixed template filled with numbers read from results / FotMob fields.
"""
