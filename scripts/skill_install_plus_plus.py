from __future__ import annotations

import os
from pathlib import Path
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("SKILL_INSTALL_PLUS_PLUS_PROJECT_ROOT", str(project_root))
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from skill_install_plus_plus.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
