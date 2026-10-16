"""One product version for the player, companion, and release artifacts."""
from pathlib import Path

PRODUCT_VERSION = (Path(__file__).resolve().parents[1] / 'VERSION').read_text(encoding='utf-8').strip()
