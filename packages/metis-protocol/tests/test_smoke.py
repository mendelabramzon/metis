import metis_protocol


def test_version_is_nonempty_string() -> None:
    assert isinstance(metis_protocol.__version__, str)
    assert metis_protocol.__version__
