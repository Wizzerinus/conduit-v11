import os
from functools import lru_cache
from typing import Callable, Sequence, TypeVar

import yaml

T = TypeVar("T")

# if we don't disable format, transtable becomes really long vertically and hard to read
# fmt: off
login_transtable = {
    " ": "_", "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya"
}
# fmt: on


@lru_cache
def get_config(filename: str) -> dict:
    with open(f"config/{filename}.yml", "r") as f:
        return yaml.safe_load(f)


def get_environment_config() -> dict:
    if not os.getenv("PYC_PRODUCTION", ""):
        return get_config("environments/dev")
    else:
        return get_config("environments/production")


def partition(objects: Sequence[T], count: int, predicate: Callable[[T], int]) -> tuple[list[T], ...]:
    """Partition a list of objects into N lists based on a predicate."""
    results = tuple([[] for _ in range(count + 1)])
    for obj in objects:
        try:
            results[predicate(obj)].append(obj)
        except (TypeError, IndexError):
            results[-1].append(obj)

    return results


def transform_to_login(username: str) -> str:
    return "".join([login_transtable.get(x, x) for x in username.lower()])
