from pyconduit.shared.datastore import datastore_manager


def init_databases():
    with datastore_manager.get("sheets").operation() as ds:
        ds.get("sheets", {})
        ds.get("formulas", "")
        ds.get("aggregators", {})

    with datastore_manager.get("accounts").operation() as ds:
        ds.get("accounts", {})

    with datastore_manager.get("images").operation() as ds:
        ds.get("images", {})
