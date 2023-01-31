from typing import cast

from pydantic import BaseModel

from pyconduit.models.conduit import Conduit, ConduitContent
from pyconduit.models.latex import LatexDocument


class BundleDocument(BaseModel):
    latex: LatexDocument = None
    conduit: Conduit = None
    precomputed: ConduitContent = None

    @classmethod
    def parse_obj(cls, data) -> "BundleDocument":
        # This is needed because LatexDocument overrides parse_obj and Pydantic prefers the constructor
        if "latex" in data:
            data = dict(data)
            data["latex"] = LatexDocument.parse_obj(data["latex"])
        return cast(BundleDocument, super().parse_obj(data))


class Aggregator(BaseModel):
    name: str
    extra_columns: list[str] = []
    extra_rows: list[str] = []
    show_columns: bool = False
    show_rows: bool = True
    public: bool = False
