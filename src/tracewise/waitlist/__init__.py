"""Early-access waitlist for the Tracewise website (pre-release signups).

Self-contained: its own settings, schema (`waitlist`), migration chain, database role and process. It never
imports the GitHub App's runtime modules and has no access to product tables.
"""
