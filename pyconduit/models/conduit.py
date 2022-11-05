from pydantic import BaseModel

from pyconduit.models.user import UserSensitive

"""
Conduit generation strategies:
Note that if the conduit has to be rebuilt and the author cannot edit them, a warning is emitted.

* 'none' - conduit is not generated at all.
* 'once' - conduit is generated if the bundle has no conduit yet.
* 'force' - ask the person saving the latex file for confirmation or to change the strategy.
  Wipes all conduit data in the process, so not recommended to be used after the sheet is publicly available.
  Note that we cannot change the strategy on the file source because the commands require having a syntax tree already.
* 'cache-soft' - attempt to use the cached problem texts. If a problem is not found, do not generate conduit.
* 'cache-optimal' - attempt to use the cached problem texts. If a problem is not found, but all cached problems are in
  the latex file, reorder in the conduit. If a problem also went missing, do not generate conduit and emit a warning.
* 'cache-strong' - same with cache-optimal, but if an unknown problem is between two known ones, update its text
  in the cache first. This can apply to any number of problems.

We currently have 'none', 'once', 'force' and 'cache-optimal' implemented. Eventually we might do more.
while cache-strong sounds good in theory, it is hard to write and causes data loss in certain scenarios.
"""


class Conduit(BaseModel):
    # user -> [problem1, problem2, ...]
    content: dict[str, list[str]]
    problem_names: list[str]
    problem_text_cache: list[str]


class ConduitContent(BaseModel):
    id: str
    conduit: Conduit
    users: list[UserSensitive]
    name: str
    formula_error: str = ""
    styles: dict[str, dict[str, str]] = {}
    real_indices: list[int] = []  # old index for problems, -1 for virtual columns like "sum"
