from __future__ import annotations

import os
from pathlib import Path

# Keep relative paths predictable when launched by double-click.
os.chdir(Path(__file__).resolve().parent)

from dds_companion_patchxx import main

raise SystemExit(main())
