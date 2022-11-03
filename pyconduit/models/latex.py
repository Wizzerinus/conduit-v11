import abc

from pydantic import BaseModel

from pyconduit.shared.datastore import datastore_manager

datastore = datastore_manager.get("sheets")


class LatexObject(BaseModel, abc.ABC):
    cls: str = "undefined"

    @classmethod
    def parse_obj(cls, data: dict):
        object_types = {"text": LatexText, "problem": LatexProblem, "inc": LatexInclude, "tikz": TikzObject}
        if data["cls"] not in object_types:
            raise ValueError(f"Invalid object type: {data['cls']}")

        return object_types[data["cls"]](**data)

    def make_string(self, allow_recursion: bool = True) -> str:
        pass


class LatexText(LatexObject):
    cls = "text"
    text: str

    def make_string(self, allow_recursion: bool = True) -> str:
        return self.text


class TikzObject(LatexText):
    cls = "tikz"

    def make_string(self, allow_recursion: bool = True) -> str:
        return ""


class LatexProblem(LatexObject):
    cls = "problem"
    text: str
    num: str
    conduit_num: str
    conduit_include: bool = True

    def make_string(self, allow_recursion: bool = True) -> str:
        return f"**{self.num}** {self.text}"


class LatexInclude(LatexObject):
    cls = "inc"
    path: str

    def make_string(self, allow_recursion: bool = True) -> str:
        if not allow_recursion:
            raise ValueError(f"Multi-layer recursion detected @ {self.path}")

        if self.path not in datastore:
            raise ValueError(f"Invalid include path: {self.path}")
        doc = LatexDocument.parse_obj(datastore[self.path])
        return doc.generate_markdown(allow_recursion=False)


class LatexDocument(BaseModel):
    objects: list[LatexObject]
    orig_doc: str
    sheet_id: str = ""
    sheet_name: str = ""

    @classmethod
    def parse_obj(cls, data):
        data = dict(data)
        objects = []
        for obj in data["objects"]:
            objects.append(LatexObject.parse_obj(obj))
        data["objects"] = objects
        return super().parse_obj(data)

    def generate_markdown(self, allow_recursion: bool = True) -> str:
        object_texts = [obj.make_string(allow_recursion) for obj in self.objects]
        return "\n\n".join(object_texts)


class LatexRequest(BaseModel):
    file_content: str
    expected_sheet: str
