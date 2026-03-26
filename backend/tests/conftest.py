import os
import pytest

from backend.src.ingestion.custom_data_generator import generate_dataset


@pytest.fixture(scope='session', autouse=True)
def seeded_dataset(tmp_path_factory):
    """Generate a small deterministic dataset for tests and expose its path.

    Use `tmp_path_factory` because this fixture is session-scoped.
    """
    # Always generate a deterministic, small dataset for tests and expose its path.
    out_path = tmp_path_factory.mktemp('synthetic')
    out = str(out_path)
    os.makedirs(out, exist_ok=True)
    generate_dataset(output=out, hours=1, seed=42)
    os.environ['TEST_DATA_DIR'] = out
    return out
