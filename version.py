"""Single source of truth for the app version, baked into the frozen exe.

Bump this and tag the matching commit `vX.Y` when cutting a release — the
GitHub Actions workflow (.github/workflows/*.yml) builds + publishes the
release that update_check.py polls for.
"""

__version__ = "1.67"
