"""Guard: requirements.txt (what the Docker image installs) must track pyproject.

The Dockerfile installs from requirements.txt, exported from uv.lock. If a
dependency is added to pyproject.toml without re-exporting, prod silently
ships without it. Regenerate with:
    uv lock && uv export --frozen --no-dev --no-emit-project -o requirements.txt
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def test_every_pyproject_dep_is_pinned_in_requirements():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    reqs = (ROOT / "requirements.txt").read_text().lower()
    for dep in pyproject["project"]["dependencies"]:
        name = re.split(r"[\[><=!~; ]", dep, maxsplit=1)[0].strip().lower().replace("_", "-")
        assert re.search(rf"^{re.escape(name)}==", reqs, re.M), (
            f"'{name}' is in pyproject.toml but not pinned in requirements.txt — "
            "run: uv lock && uv export --frozen --no-dev --no-emit-project -o requirements.txt"
        )
