"""Automatic result tracking of the two headline picks (Banko and Oranlı) of a match.

* ``records``  - frozen picks in the prediction_versions table (stages headline_banko / headline_oranli)
* ``results``  - where the final result comes from and how a pick is settled
* ``sources``  - default fixture / prediction / line-up sources (reuse the existing provider chain)
* ``tracker``  - the background loop (freeze ~20 min before kick-off, settle after full time)
* ``report``   - read side for the API (hit rate per kind, competition, week)
* ``backfill`` - import of the hand-tracked night of 2026-10-14

The selection rule itself lives in app/prediction/headline_picks.py (port of the frontend rule).
"""
