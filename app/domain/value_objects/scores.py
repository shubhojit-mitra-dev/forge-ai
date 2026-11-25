from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ScoreBreakdown:
    """Aggregated evaluation metrics for an agent run."""

    total_cases: int
    passed_cases: int
    grounded_count: int
    correct_count: int
    refusal_accurate_count: int

    def _ratio(self, numerator: int) -> float:
        if self.total_cases == 0:
            return 0.0
        return numerator / self.total_cases

    @property
    def pass_rate(self) -> float:
        return self._ratio(self.passed_cases)

    @property
    def grounded_rate(self) -> float:
        return self._ratio(self.grounded_count)

    @property
    def correct_rate(self) -> float:
        return self._ratio(self.correct_count)

    @property
    def refusal_accuracy(self) -> float:
        return self._ratio(self.refusal_accurate_count)
