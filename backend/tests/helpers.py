import os


def sample_path(filename: str) -> str:
    base = os.environ.get('TEST_DATA_DIR')
    if not base:
        raise RuntimeError('TEST_DATA_DIR is not set; tests expect generated dataset to be available via the seeded fixture')
    return os.path.join(base, filename)
