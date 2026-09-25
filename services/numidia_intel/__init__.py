"""NUMIDIA EYE intelligence layer (backend, read-mostly).

Pure domain services over the production SQLite database. No ingestion logic
here, no model training, no fabricated values: every unavailable input is
reported as UNAVAILABLE with a reason, never guessed.
"""
