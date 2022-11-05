import abc
import contextlib
import json
import logging
import os
import traceback

from pyconduit.shared.helpers import get_environment_config

DatastoreSentinel = object()
cfg = get_environment_config()


def atomize(parent, value, path):
    if isinstance(value, dict):
        return AtomicDict(parent, {k: atomize(parent, v, f"{path}{k}.") for k, v in value.items()}, path)
    elif isinstance(value, list):
        return AtomicList(parent, [atomize(parent, v, f"{path}{i}.") for i, v in enumerate(value)], path)
    else:
        return value


def deatomize(value):
    if isinstance(value, AtomicDict) or isinstance(value, AtomicList):
        return deatomize(value._data)
    elif isinstance(value, dict):
        return {k: deatomize(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [deatomize(v) for v in value]
    else:
        return value


class AtomicList:
    def __init__(self, parent=None, data=None, path=""):
        self.parent = parent if parent is not None else self
        self._data = data
        self.path = path
        if parent is not None:
            self.updates = parent.updates
        else:
            self.updates = {}

    def direct_set(self, key, value):
        self._data[key] = value

    def direct_append(self, value):
        self._data.append(value)

    def append(self, value):
        dataLen = len(self._data)
        self._data.append(atomize(self.parent, value, f"{self.path}{dataLen}."))
        self.updates[f"{self.path}append[{dataLen}]"] = value

    def __getitem__(self, item):
        return self._data[item]

    def __setitem__(self, key, value):
        self._data[key] = atomize(self.parent, value, f"{self.path}{key}.")
        self.updates[f"{self.path}{key}"] = value

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, item):
        return item in self._data

    def __repr__(self):
        return f"AtomicList({self._data})"


class AtomicDict:
    ExistingAttrs = {"path", "_data", "parent", "updates", "ExistingAttrs"}

    def __init__(self, parent=None, data=None, path=""):
        self.path = path
        self._data = data or {}
        self.parent = parent if parent is not None else self
        if parent is not None:
            self.updates = parent.updates
        else:
            self.updates = {}
        assert self.updates is self.parent.updates

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = atomize(self.parent, value, f"{self.path}{key}.")
        self.updates[f"{self.path}{key}"] = deatomize(value)

    def __getattr__(self, key):
        if key not in self.ExistingAttrs:
            return self[key]
        else:
            return super().__getattribute__(key)

    def __setattr__(self, key, value):
        if key not in self.ExistingAttrs:
            self[key] = value
        else:
            super().__setattr__(key, value)

    def __delitem__(self, key):
        del self._data[key]
        self.updates[f"{self.path}{key}"] = None

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def __len__(self):
        return len(self._data)

    def __contains__(self, item):
        return item in self._data

    def get(self, key, defaultValue=None):
        sent = self._data.get(key, DatastoreSentinel)
        if sent is not DatastoreSentinel:
            return atomize(self.parent, sent, f"{self.path}{key}.")
        self[key] = defaultValue
        return self[key]

    def pop(self, key, default=None):
        value = self._data.pop(key, default)
        self.updates[f"{self.path}{key}"] = None
        return value

    def direct_update(self, **kwargs):
        for k, v in kwargs.items():
            self._data[k] = atomize(self.parent, v, f"{self.path}{k}.")

    def direct_set(self, key, value):
        self._data[key] = value

    def __repr__(self):
        return f"AtomicDict({self._data})"


class DatastoreHandle(abc.ABC):
    logger = logging.getLogger("PyConduit.Datastore")
    ExistingAttrs = {"category", "data", "shared", "ExistingAttrs"}

    def __init__(self, category: str, shared: bool = False):
        self.category = category
        self.data = atomize(None, {}, "")
        self.data.direct_update(**self.requestLoad())
        self.shared = shared

    def __setitem__(self, key, value):
        self.data[key] = value

    def __getitem__(self, key):
        return self.data[key]

    def __getattr__(self, key):
        if key not in self.ExistingAttrs:
            return self[key]
        else:
            return super().__getattribute__(key)

    def __setattr__(self, key, value):
        if key not in self.ExistingAttrs:
            self[key] = value
        else:
            super().__setattr__(key, value)

    def __contains__(self, item):
        return item in self.data

    def __delitem__(self, key):
        del self.data[key]

    def get(self, key, defaultValue=None):
        sent = self.data.get(key, DatastoreSentinel)
        if sent is not DatastoreSentinel:
            return atomize(self.data, sent, f"{key}.")
        self.data[key] = atomize(self.data, defaultValue, f"{key}.")
        return self.data[key]

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    @staticmethod
    def updateAtomic(fullData, changes):
        changes = {k: v for k, v in sorted(changes.items(), key=lambda x: x[0].count("."))}
        for key, value in changes.items():
            data = fullData

            path = key.split(".")
            for k in path[:-1]:
                if isinstance(data, list) or isinstance(data, AtomicList):
                    k = int(k)
                data = data[k]

            if value is None:
                del data[path[-1]]
            elif path[-1].startswith("append["):
                k = int(path[-1][7:-1])
                for i in range(k - len(data) + 1):
                    if isinstance(data, AtomicList):
                        data.direct_append(None)
                    else:
                        data.append(None)

                if isinstance(data, AtomicList):
                    data.direct_set(k, value)
                else:
                    data[k] = value
            else:
                if isinstance(data, AtomicList) or isinstance(data, list):
                    key = int(path[-1])
                else:
                    key = path[-1]

                if isinstance(data, AtomicList) or isinstance(data, AtomicDict):
                    data.direct_set(key, value)
                else:
                    data[key] = value

    def updateAtomicSafe(self, data, changes):
        try:
            self.updateAtomic(data, changes)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError):
            self.logger.warning(f"Invalid update: {changes}")
            traceback.print_exc()
            return False
        return True

    def save(self, otherUpdates=None):
        updates = dict(self.data.updates)
        if otherUpdates:
            updates.update(otherUpdates)
        self.data.updates.clear()
        if not updates:
            return

        self.saveAtomic(updates)

    def sync(self, updates):
        self.updateAtomicSafe(self.data, updates)

    @contextlib.contextmanager
    def operation(self):
        yield self
        self.save()

    @abc.abstractmethod
    def requestLoad(self):
        """
        Request the data to be loaded. Runs synchronously and should return the data as a dictionary.
        """

    @abc.abstractmethod
    def saveAtomic(self, data):
        """
        Request the list of the given updates to be saved. May run in background.
        """

    @abc.abstractmethod
    def wipe(self):
        """
        Request the data to be wiped. May run in background.
        """


class DatastoreJSON(DatastoreHandle):
    baseDataFolder = cfg["datastore"]["data-folder"]
    ExistingAttrs = DatastoreHandle.ExistingAttrs | {"filename", "baseDataFolder"}

    def __init__(self, category: str, sharedLock: bool = None):
        self.filename = f"{self.baseDataFolder}/{category}.json"
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        super().__init__(category, sharedLock)

    def requestLoad(self) -> dict:
        try:
            with open(self.filename, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            with open(self.filename, "w") as f:
                f.write("{}")
            return {}

    def saveAtomic(self, updates: dict) -> None:
        # Dumping into string instead of the stream to prevent partial writes which corrupt the file
        with open(self.filename, "r") as f:
            data = json.load(f)

        self.updateAtomicSafe(data, updates)
        try:
            out = json.dumps(data, indent=2)
        except TypeError:
            self.logger.warning(f"Invalid data: {data}")
            traceback.print_exc()
            return

        with open(self.filename, "w") as f:
            f.write(out)

    def wipe(self) -> None:
        try:
            os.remove(f"{self.baseDataFolder}/{self.category}.json")
        except FileNotFoundError:
            pass


class DatastoreManager:
    logger = logging.getLogger("PyConduit.DatastoreManager")

    dbBackends = {
        "json": DatastoreJSON,
    }

    def __init__(self, dbBackend: str, prefix: str = None):
        self.datastores = {}
        self.sharedLocks = {}
        self.prefix = prefix

        assert dbBackend in self.dbBackends, f"Invalid datastore backend: {dbBackend}"
        self.accountCtor = self.dbBackends[dbBackend]

    def get(self, name: str) -> DatastoreHandle:
        usesOverride = True
        if "/" not in name and self.prefix is not None:
            usesOverride = False
            name = f"{self.prefix}/{name}"
        if name not in self.datastores:
            self.datastores[name] = self.accountCtor(name, usesOverride)
        return self.datastores[name]


datastore_manager = DatastoreManager(cfg["datastore"]["backend"])
