"""Exception classes for Vdebug."""


class BreakpointError(Exception):
    pass


class UserInterrupt(Exception):
    """Raised when a user interrupts connection wait."""
    pass


class FilePathError(Exception):
    pass


class EventError(Exception):
    pass


class LogError(Exception):
    pass


class ModifiedBufferError(Exception):
    pass


class NoConnectionError(Exception):
    pass
