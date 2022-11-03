import os
from functools import lru_cache

import yaml


@lru_cache
def get_config(filename: str) -> dict:
    with open(f"config/{filename}.yml", "r") as f:
        return yaml.safe_load(f)


def get_environment_config() -> dict:
    if not os.getenv("PYC_PRODUCTION", ""):
        return get_config("environments/dev")
    else:
        return get_config("environments/production")
