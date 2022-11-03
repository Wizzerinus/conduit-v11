from pydantic import BaseModel, constr


class Privileges(BaseModel):
    login: bool = True
    admin: bool = False
    conduit_generation: bool = True
    conduit_edit: bool = False
    sheets_edit: bool = False

    def has_scope(self, scope: str) -> bool:
        return getattr(self, scope, False)

    def __iter__(self):
        return (key for key, value in self.__dict__.items() if value)


class User(BaseModel):
    login: str
    password: str
    salt: str
    name: str
    privileges: Privileges


class RegisterUser(BaseModel):
    login: str
    password: constr(min_length=6, max_length=64)
    name: str
    privileges: Privileges
