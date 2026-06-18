import metis_core


def test_version_is_nonempty_string() -> None:
    assert isinstance(metis_core.__version__, str)
    assert metis_core.__version__
