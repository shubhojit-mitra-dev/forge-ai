class ForgeDomainError(Exception):
    """Base exception for all ForgeAI domain invariant violations."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


class GroundabilityBlockedError(ForgeDomainError):
    """Raised when required topics cannot be grounded in uploaded documents."""


class BudgetExceededError(ForgeDomainError):
    """Raised when an execution exceeds its iteration, token, or cost budget."""


class InvalidToolSelectionError(ForgeDomainError):
    """Raised when an agent selects an unsupported or unjustified tool."""


class EntityNotFoundError(ForgeDomainError):
    """Raised when a requested domain aggregate or entity does not exist."""


class ValidationDomainError(ForgeDomainError):
    """Raised when a domain entity or value object invariant is violated."""
