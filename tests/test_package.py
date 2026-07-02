def test_package_exposes_version() -> None:
    import muse

    assert muse.__version__ == "0.1.0"
