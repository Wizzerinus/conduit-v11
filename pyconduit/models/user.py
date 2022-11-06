from pydantic import BaseModel, constr


class Privileges(BaseModel):
    login: bool = True
    admin: bool = False
    conduit_generation: bool = True
    conduit_edit: bool = False
    sheets_edit: bool = False
    formula_edit: bool = False
    technical_operations: bool = False

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
    virtual: bool = False

    allow_conduit_view: bool = True


class UserSensitive(BaseModel):
    login: str
    name: str
    privileges: Privileges = None
    virtual: bool = False


class RegisterUser(BaseModel):
    login: str
    password: constr(min_length=6, max_length=64)
    name: str
    privileges: Privileges


class BulkRegister(BaseModel):
    teachers: bool
    users: str


class AuthorizedRequest(BaseModel):
    current_password: str


class ChangePasswordRequest(AuthorizedRequest):
    new_password: str
    new_password_confirm: str


class ConduitSettingsRequest(AuthorizedRequest):
    allow_conduit_view: bool
