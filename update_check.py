"""Checks GitHub for a newer release than the version baked into this build.

Desktop users grab the exe once and may never come back to check for
updates, unlike a hosted site where everyone is always on the latest code.
This is a best-effort, fail-silent check — no internet access or GitHub
being unreachable must never block or break the app.
"""
import json
import urllib.error
import urllib.request

from version import __version__

REPO = "napkingcole/aoe2-empire-forge"
_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"


def _parse_version(v: str) -> tuple[int, ...]:
    parts = []
    for p in v.lstrip("vV").split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_update(timeout: float = 3.0) -> dict | None:
    """Return {"current", "latest", "url"} if a newer release exists, else None."""
    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "AOE2EmpireForge"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        latest = str(data["tag_name"]).lstrip("vV")
        if _parse_version(latest) > _parse_version(__version__):
            return {"current": __version__, "latest": latest, "url": RELEASES_URL}
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        pass
    return None
