class UnauthorizedAccessError(Exception):
    """Exception raised when a user tries to access a resource they don't have permission for"""

    def __init__(self, message="You do not have permission to access this resource"):
        self.message = message
        super().__init__(self.message)
