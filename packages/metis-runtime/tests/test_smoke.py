import metis_runtime


def test_version_is_nonempty_string() -> None:
    assert isinstance(metis_runtime.__version__, str)
    assert metis_runtime.__version__
