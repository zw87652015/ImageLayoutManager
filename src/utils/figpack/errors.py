"""Exception hierarchy for figpack operations."""


class BundleError(Exception):
    """Raised for any unrecoverable problem with a .figpack archive.

    The message is intended to be user-facing; callers should feed it
    through the existing i18n layer before displaying. ``code`` is a
    stable short identifier for tests and telemetry.
    """

    def __init__(self, message: str, *, code: str = "bundle_error"):
        super().__init__(message)
        self.code = code


class BundleSecurityError(BundleError):
    """Raised for any extraction rule violation (zip-slip, bomb, …).

    A separate subclass so security-sensitive checks can be caught
    specifically without masking genuine IO errors.
    """

    def __init__(self, message: str, *, code: str = "security"):
        super().__init__(message, code=code)


class BundleIntegrityError(BundleError):
    """Raised when an on-disk hash does not match ``metadata.json``."""

    def __init__(self, message: str, *, code: str = "integrity"):
        super().__init__(message, code=code)
