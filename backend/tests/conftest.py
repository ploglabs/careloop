import os
import tempfile

# Isolated database and no external services for every test run.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CARELOOP_SCHEDULER"] = "0"
os.environ["LLM_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["GNANI_API_KEY"] = ""

import pytest  # noqa: E402

from careloop.seed import build  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    build(history=True)
    yield
