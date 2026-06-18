import metis_skills


def test_version_is_nonempty_string() -> None:
    assert isinstance(metis_skills.__version__, str)
    assert metis_skills.__version__
