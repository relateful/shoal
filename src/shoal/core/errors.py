"""The root of every exception Shoal raises."""


class ShoalError(Exception):
    """Base class for all Shoal exceptions, so callers can catch the library as a whole."""


class MissingDependencyError(ShoalError):
    """An optional feature was requested without its optional dependency installed."""

    def __init__(self, feature: str, extra: str) -> None:
        """Report that `feature` needs `pip install shoal[extra]`."""
        super().__init__(f"{feature} requires the optional dependency: pip install 'shoal[{extra}]'")
        self.feature: str = feature
        self.extra: str = extra
