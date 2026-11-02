import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="mediacraft-test-")
os.environ["MEDIACRAFT_CONFIG_DIR"] = os.path.join(_TMP, "config")
os.environ["MEDIACRAFT_DISABLE_SCHEDULER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return Path(_TMP)


@pytest.fixture(scope="session", autouse=True)
def database():
    from app.db import init_db

    init_db()
    yield
