import metis_maintainer


def test_version_is_nonempty_string() -> None:
    assert isinstance(metis_maintainer.__version__, str)
    assert metis_maintainer.__version__
