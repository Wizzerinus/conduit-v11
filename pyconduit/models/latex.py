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

    def newline_before(self) -> bool:
        return True

    def newline_after(self) -> bool:
        return True


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
    nlb: bool
    nla: bool
    conduit_include: bool = True

    def make_string(self, allow_recursion: bool = True) -> str:
        return f"**{self.num}** {self.text}"

    def newline_before(self) -> bool:
        return self.nlb

    def newline_after(self) -> bool:
        return self.nla


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
        object_texts = []
        for obj in self.objects:
            current_text = obj.make_string(allow_recursion)
            if obj.newline_after():
                current_text += "\n\n"
            else:
                current_text += "\\\n"

            if obj.newline_before():
                current_text = "\n" + current_text
            object_texts.append(current_text)

        return "".join(object_texts).replace("\\\n\n", "\n\n")


class LatexRequest(BaseModel):
    file_content: str
    expected_sheet: str
