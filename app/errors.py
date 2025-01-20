class DatabaseError(Exception):
    """A custom exception for errors occurring during database operations."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
