import pytest

from app.domain.exceptions import (
    BudgetExceededError,
    EntityNotFoundError,
    ForgeDomainError,
    GroundabilityBlockedError,
    InvalidToolSelectionError,
    ValidationDomainError,
)


@pytest.mark.unit
class TestDomainExceptions:
    def test_base_exception_stores_code_and_detail(self) -> None:
        err = ForgeDomainError(code="domain_error", detail="Something went wrong")
        assert isinstance(err, Exception)
        assert err.code == "domain_error"
        assert err.detail == "Something went wrong"
        assert "domain_error" in str(err)
        assert "Something went wrong" in str(err)

    @pytest.mark.parametrize(
        ("exc_cls", "code", "detail"),
        [
            (GroundabilityBlockedError, "groundability_blocked", "Missing grounding docs"),
            (BudgetExceededError, "budget_exceeded", "Token budget exhausted"),
            (InvalidToolSelectionError, "invalid_tool", "weather_http not needed"),
            (EntityNotFoundError, "not_found", "Project not found"),
            (ValidationDomainError, "validation_error", "Invalid iteration count"),
        ],
    )
    def test_subclasses_inherit_from_forge_domain_error(
        self,
        exc_cls: type[ForgeDomainError],
        code: str,
        detail: str,
    ) -> None:
        err = exc_cls(code=code, detail=detail)
        assert isinstance(err, ForgeDomainError)
        assert err.code == code
        assert err.detail == detail
