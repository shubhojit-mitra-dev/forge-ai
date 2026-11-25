# ForgeAI Data Contracts & API Specifications

All backend DTOs use **Pydantic v2** with `Annotated[...]` constraints and `ConfigDict(frozen=True)` where immutable. Domain entities use `@dataclass(slots=True)`.

---

## 1. Core Domain Contracts

### 1.1 `RequirementsDoc` (Output of Stage 1: Intake Interviewer)
```python
class RequirementsDoc(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_name: Annotated[str, Field(min_length=3, max_length=80)]
    scope: Annotated[str, Field(min_length=10)]
    target_audience: Annotated[str, Field(min_length=3)]
    tone: Annotated[str, Field(min_length=3)]
    must_answer_topics: Annotated[list[str], Field(min_length=1)]
    must_refuse_topics: Annotated[list[str], Field(min_length=1)]
    clarifying_qa: list[ClarifyingQA]  # Max 5 questions enforced
    detected_tool_needs: list[ToolName]
```

### 1.2 `GroundabilityReport` (Output of Stage 2: Groundability Guard)
```python
class TopicGroundability(BaseModel):
    topic: str
    is_grounded: bool
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    supporting_documents: list[str]
    gap_reason: str | None = None

class GroundabilityReport(BaseModel):
    is_passable: bool
    critical_gaps: list[TopicGroundability]
    warnings: list[TopicGroundability]
    summary: str
```
*Rule:* If `critical_gaps` is non-empty for a `must_answer_topic`, the factory **halts or flags** before Agent Generation—never silently hallucinating coverage.

### 1.3 `AgentDefinition` (Output of Stage 3: Agent Generator)
```python
class RetrievalConfig(BaseModel):
    chunk_size: Annotated[int, Field(ge=200, le=2000)] = 600
    chunk_overlap: Annotated[int, Field(ge=0, le=400)] = 100
    top_k: Annotated[int, Field(ge=1, le=15)] = 5
    similarity_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.35
    hybrid_search: bool = True

class OutputContract(BaseModel):
    format: Literal["markdown", "json"] = "markdown"
    require_citations: bool = True
    refusal_template: str
    max_response_words: Annotated[int, Field(ge=50, le=1000)] = 350

class AgentDefinition(BaseModel):
    id: UUID
    project_id: UUID
    slug: str
    version: Annotated[int, Field(ge=1)]
    system_prompt: Annotated[str, Field(min_length=50)]
    retrieval_config: RetrievalConfig
    selected_tools: list[ToolName]  # Subset of ["csv_lookup", "calculator", "weather_http", "current_date"]
    output_contract: OutputContract
```

### 1.4 `EvalCase`, `JudgeScore`, `IterationLog`, `HonestReport` (Stages 4–7)
```python
class EvalCaseType(str, Enum):
    ANSWERABLE = "answerable"
    REFUSAL = "refusal"
    EDGE = "edge"

class FailureCategory(str, Enum):
    NONE = "none"
    RETRIEVAL_MISS = "retrieval_miss"
    PROMPT_DEFECT = "prompt_defect"
    HALLUCINATION = "hallucination"
    WRONG_REFUSAL = "wrong_refusal"

class EvalCase(BaseModel):
    id: UUID
    case_type: EvalCaseType
    question: str
    expected_sources: list[str]
    expected_facts: list[str]
    should_refuse: bool
    rationale: str

class JudgeScore(BaseModel):
    eval_case_id: UUID
    grounded: bool
    correct: bool
    refusal_accurate: bool
    passed: bool
    failure_category: FailureCategory
    reasoning: str
    deterministic_checks: dict[str, bool]

class IterationLog(BaseModel):
    iteration: Annotated[int, Field(ge=1, le=3)]
    score_before: Annotated[float, Field(ge=0.0, le=1.0)]
    score_after: Annotated[float, Field(ge=0.0, le=1.0)]
    failures_addressed: list[UUID]
    change_type: Literal["retrieval_config", "system_prompt", "output_contract", "tool_selection"]
    what_changed: str
    why: str

class HonestReport(BaseModel):
    project_id: UUID
    final_agent_version: int
    per_iteration_scores: list[dict[str, float | int]]
    final_pass_rate: float
    remaining_failures: list[dict[str, str]]
    known_limitations: list[str]
    recommendation: str
```

---

## 2. Tool Registry Protocol (`domain/protocols/tool.py`)

```python
class ToolName(str, Enum):
    CSV_LOOKUP = "csv_lookup"
    CALCULATOR = "calculator"
    WEATHER_HTTP = "weather_http"
    CURRENT_DATE = "current_date"

class AgentToolProtocol(Protocol):
    @property
    def name(self) -> ToolName: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters_schema(self) -> dict[str, Any]: ...
    async def execute(self, **kwargs: Any) -> str: ...
```

---

## 3. REST & Streaming API Endpoints

All endpoints prefixed with `/api/v1` and protected by Supabase JWT (`Authorization: Bearer <token>`), except `/api/v1/agents/public/{slug}/chat` for published runnable agents.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + LiteLLM + Supabase health check |
| `POST` | `/projects` | Create ForgeAI project from initial brief |
| `GET` | `/projects` | List user's projects (sidebar history) |
| `GET` | `/projects/{id}` | Get full project state, artifacts, latest evals |
| `POST` | `/projects/{id}/documents` | Upload PDF/CSV/MD/TXT → Supabase Storage + chunk + embed |
| `POST` | `/projects/{id}/intake/start` | Generate ≤5 clarifying questions from brief + docs |
| `POST` | `/projects/{id}/intake/submit` | Submit answers → produces `RequirementsDoc` + runs `GroundabilityGuard` |
| `POST` | `/projects/{id}/forge/run` | Trigger unattended ForgeAI pipeline (Generator → Evals → Judge → Critic Loop ≤3 → Report) |
| `GET` | `/projects/{id}/forge/stream` | SSE stream of live pipeline events (`stage_started`, `eval_scored`, `iteration_complete`, `forge_finished`) |
| `GET` | `/projects/{id}/artifacts` | Download/export all JSON + Markdown artifacts for git commit |
| `GET` | `/agents/public/{slug}` | Fetch public metadata for `/agent/[slug]` UI |
| `POST` | `/agents/public/{slug}/chat` | Generic runnable agent chat endpoint (RAG + selected tools + output contract) |

