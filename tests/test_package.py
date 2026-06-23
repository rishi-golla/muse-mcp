def test_package_exposes_version() -> None:
    import creativity_layer

    assert creativity_layer.__version__ == "0.1.0"
