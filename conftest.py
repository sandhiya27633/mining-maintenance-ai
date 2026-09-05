# conftest.py — pytest project-root configuration
# Adds src/ to sys.path so all test imports resolve cleanly
# without needing to install the package.

import sys
from pathlib import Path

# Insert src/ at position 0 so test imports like `import config` work directly.
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
