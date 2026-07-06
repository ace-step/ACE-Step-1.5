"""Exceptions raised by device-map parsing and resolution."""


class DeviceMapError(ValueError):
    """Raised when a GPU mapping string cannot be parsed or validated."""
