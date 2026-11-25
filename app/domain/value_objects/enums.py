from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFTING = "drafting"
    INTAKE = "intake"
    BLOCKED = "blocked"
    FORGING = "forging"
    READY = "ready"
    FAILED = "failed"


class EvalCaseType(StrEnum):
    ANSWERABLE = "answerable"
    REFUSAL = "refusal"
    EDGE = "edge"


class FailureCategory(StrEnum):
    NONE = "none"
    RETRIEVAL_MISS = "retrieval_miss"
    PROMPT_DEFECT = "prompt_defect"
    HALLUCINATION = "hallucination"
    WRONG_REFUSAL = "wrong_refusal"


class ToolName(StrEnum):
    CSV_LOOKUP = "csv_lookup"
    CALCULATOR = "calculator"
    WEATHER_HTTP = "weather_http"
    CURRENT_DATE = "current_date"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED_EARLY = "stopped_early"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChangeType(StrEnum):
    RETRIEVAL_CONFIG = "retrieval_config"
    SYSTEM_PROMPT = "system_prompt"
    OUTPUT_CONTRACT = "output_contract"
    TOOL_SELECTION = "tool_selection"
