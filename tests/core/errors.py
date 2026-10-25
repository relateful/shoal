from shoal.core.errors import MissingDependencyError, ShoalError


def test_missing_dependency_names_the_extra_to_install() -> None:
    error = MissingDependencyError("zstd-stream gateway compression", "zstd")
    assert isinstance(error, ShoalError)
    assert error.extra == "zstd"
    assert "pip install 'shoal[zstd]'" in str(error)
