# Smoke test: package imports.


def test_import_brig():
    import brig

    assert brig is not None
