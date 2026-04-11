"""
GDPR Scanner — Flask route blueprints.

Each module registers one Blueprint and imports shared state from
gdpr_scanner (the application entry point).  Import order matters:
blueprints must be registered after `app` and all shared globals
(flagged_items, _connector, etc.) are defined.
"""
