import metis_ingestion


def test_version_is_nonempty_string() -> None:
    assert isinstance(metis_ingestion.__version__, str)
    assert metis_ingestion.__version__
