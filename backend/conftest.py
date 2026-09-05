"""backend/conftest.py — pytest configuration for backend tests."""
import sys
from pathlib import Path

# Make app/ and app/engine/ importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app" / "engine"))
