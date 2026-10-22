"""Pictures from the player's own game files, made ready to show.

A unit icon in `widgetui/textures/ingame/units` is a DDS whose alpha channel is
the player-colour mask — where the game paints team colour — not transparency.
Shown as transparency it cut holes in Bohemond's helmet and tabard; flattened
it was grey.  icon_rgb() paints the mask Player 1 Blue, as the game would for
player 1, the same blue the sprite previews use.
"""
from pathlib import Path

import numpy as np
from PIL import Image

# Player 1 Blue, as the previews tint it (shaded by the art's own brightness).
PLAYER_BLUE = np.array([45, 100, 230], dtype=np.float32)


def player_tint(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """rgb (H, W, 3) float, mask (H, W, 1) in 0..1 = how much is player colour."""
    lum = rgb.mean(axis=2, keepdims=True) / 255.0
    return rgb * (1 - mask) + PLAYER_BLUE * np.clip(lum * 1.6, 0, 1) * mask


def icon_rgb(path: Path) -> Image.Image:
    """A game unit icon as an opaque RGB image, its mask painted Player 1 Blue."""
    a = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)
    out = player_tint(a[..., :3], 1 - a[..., 3:4] / 255.0)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGB")
