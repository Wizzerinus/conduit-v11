from pydantic import BaseModel

from pyconduit.models.user import UserUnprivileged

"""
Conduit generation strategies:
Note that if the conduit has to be rebuilt and the author cannot edit them, a warning is emitted.

* 'none' - conduit is not generated at all.
* 'once' - conduit is generated if the bundle has no conduit yet.
* 'force' - ask the person saving the latex file for confirmation or to change the strategy.
  Wipes all conduit data in the process, so not recommended to be used after the sheet is publicly available.
  Note that we cannot change the strategy on the file source because the commands require having a syntax tree already.
* 'wipe-cache' - check that the sizes of problem array and the problem text cache are equal, 
  and if so, regenerate the cache.
* 'cache-optimal' - attempt to use the cached problem texts. If a problem is not found, but all cached problems are in
  the latex file, reorder in the conduit. If a problem also went missing, do not generate conduit and emit a warning.
* 'wipe-removed' - if any new problems appeared, emit a warning. Otherwise, delete all missing problems.
* '__debug' - do not save the sheet, dump the current list of problems and the pending list of problems instead.
"""


class Conduit(BaseModel):
    # user -> [problem1, problem2, ...]
    content: dict[str, list[str]]
    problem_names: list[str]
    problem_text_cache: list[str]


class ConduitContent(BaseModel):
    id: str
    conduit: Conduit
    users: list[UserUnprivileged]
    name: str
    formula_error: str = ""
    styles: dict[str, dict[str, str]] = {}
    real_indices: list[int] = []  # old index for problems, -1 for virtual columns like "sum"
    limited_columns: list[str] = []
    limited_rows: list[str] = []
    column_styles: dict[str, str] = {}
    row_styles: dict[str, str] = {}
