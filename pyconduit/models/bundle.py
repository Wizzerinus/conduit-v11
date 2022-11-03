from pydantic import BaseModel

from pyconduit.models.latex import LatexDocument


class BundleDocument(BaseModel):
    latex: LatexDocument = None

    @classmethod
    def parse_obj(cls, data):
        if "latex" in data:
            data = dict(data)
            data["latex"] = LatexDocument.parse_obj(data["latex"])
        return super().parse_obj(data)
