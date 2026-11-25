"""Integration tests for the ForgeAI CLI (`forge` and `chat` subcommands)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from app.application.services.critic_optimizer import CriticOptimizerService
from app.application.services.judge_service import JudgeService
from app.application.services.reporter_service import ReporterService
from app.config import Settings
from app.domain.protocols.llm_gateway import LLMResponse
from app.infrastructure.cache.ttl_cache import InMemoryTTLCache
from app.infrastructure.parsers import CsvParser, OverlapChunker, PdfParser, TextParser
from app.infrastructure.tools.registry import get_tool_registry

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class _FakeEmbeddingGateway:
    """Deterministic embedding gateway for CLI integration tests."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lower = text.lower()
            vectors.append(
                [
                    1.0 if "leave" in lower or "hr" in lower else 0.2,
                    1.0 if "travel" in lower or "expense" in lower else 0.2,
                    1.0 if "remote" in lower else 0.2,
                    0.5,
                ]
            )
        return vectors


class _FakeLLMGateway:
    """Scripted LLM gateway responding appropriately to every ForgeAI stage."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._eval_gen_batch = 0

    async def complete(
        self,
        messages: list[dict[str, str]],
        tier: str = "orchestrator-primary",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "tier": tier,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            }
        )
        system_msg = messages[0]["content"] if messages else ""
        user_msg = messages[-1]["content"] if messages else ""
        combined = f"{system_msg}\n{user_msg}".lower()

        if "requirements synthesizer" in combined:
            payload = {
                "agent_name": "Shore HR Assistant",
                "scope": "Answer HR policy questions for shore staff based on policy docs.",
                "target_audience": "Shore-based employees",
                "tone": "Professional and concise",
                "must_answer_topics": ["Annual leave entitlement", "Travel expense claims"],
                "must_refuse_topics": ["Personal salary negotiation", "Legal advice"],
                "detected_tool_needs": ["current_date"],
            }
            return _llm_ok(json.dumps(payload))

        if "intake interviewer" in combined:
            payload = {
                "questions": [
                    "Should the assistant cite policy section numbers?",
                    "Which regions of shore staff are covered?",
                ]
            }
            return _llm_ok(json.dumps(payload))

        if "groundability" in combined:
            payload = {
                "is_grounded": True,
                "confidence": 0.92,
                "supporting_documents": ["leave_policy.md"],
                "gap_reason": None,
            }
            return _llm_ok(json.dumps(payload))

        if "agentdefinition" in combined or "retrieval_config" in combined:
            payload = {
                "system_prompt": (
                    "You are the Shore HR Assistant. Answer questions strictly from the "
                    "provided HR policy documents, cite filenames, and refuse salary/legal advice."
                ),
                "retrieval_config": {
                    "chunk_size": 600,
                    "chunk_overlap": 100,
                    "top_k": 5,
                    "similarity_threshold": 0.3,
                    "hybrid_search": True,
                },
                "selected_tools": ["current_date"],
                "output_contract": {
                    "format": "markdown",
                    "require_citations": True,
                    "refusal_template": "I cannot answer this based on the provided documents.",
                    "max_response_words": 300,
                },
            }
            return _llm_ok(json.dumps(payload))

        if "evaluation" in combined and "cases" in combined and "case_type" in combined:
            self._eval_gen_batch += 1
            cases: list[dict[str, Any]] = []
            for idx in range(12):
                cases.append(
                    {
                        "case_type": "answerable",
                        "question": f"What is the annual leave rule #{self._eval_gen_batch}-{idx}?",
                        "expected_sources": ["leave_policy.md"],
                        "expected_facts": ["20 days annual leave"],
                        "should_refuse": False,
                        "rationale": "Grounded in leave_policy.md",
                    }
                )
            for idx in range(6):
                cases.append(
                    {
                        "case_type": "refusal",
                        "question": f"Can you negotiate my salary #{self._eval_gen_batch}-{idx}?",
                        "expected_sources": [],
                        "expected_facts": [],
                        "should_refuse": True,
                        "rationale": "Out of scope refusal test",
                    }
                )
            for idx in range(4):
                cases.append(
                    {
                        "case_type": "edge",
                        "question": (
                            f"How do leave and travel overlap #{self._eval_gen_batch}-{idx}?"
                        ),
                        "expected_sources": ["leave_policy.md"],
                        "expected_facts": ["20 days annual leave"],
                        "should_refuse": False,
                        "rationale": "Edge case",
                    }
                )
            return _llm_ok(json.dumps({"cases": cases}))

        if "judge" in combined or ("grounded" in combined and "refusal_accurate" in combined):
            is_refusal_case = "negotiate my salary" in combined
            payload = {
                "grounded": True,
                "correct": True,
                "refusal_accurate": True,
                "failure_category": "none",
                "reasoning": (
                    "Correctly refused out-of-scope request."
                    if is_refusal_case
                    else "Answer is grounded in leave_policy.md with 20 days annual leave."
                ),
            }
            return _llm_ok(json.dumps(payload))

        if "critic" in combined or "failure_category" in combined:
            payload = {
                "change_type": "system_prompt",
                "what_changed": "Clarified citation instruction.",
                "why": "Ensure consistent citations.",
                "new_value": (
                    "You are the Shore HR Assistant. Always cite [leave_policy.md] and "
                    "refuse salary or legal advice."
                ),
            }
            return _llm_ok(json.dumps(payload))

        if "negotiate my salary" in combined:
            return _llm_ok("I cannot answer this based on the provided documents.")

        return _llm_ok("Shore staff receive 20 days annual leave per year [leave_policy.md].")


def _llm_ok(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="mock-model",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=10,
    )


def _build_mock_container(llm: _FakeLLMGateway, embeddings: _FakeEmbeddingGateway) -> Any:
    from app.application.container import AppContainer, ParserBundle

    return AppContainer(
        settings=Settings(),
        cache=InMemoryTTLCache(maxsize=128, default_ttl_seconds=60),
        llm_gateway=llm,  # type: ignore[arg-type]
        embedding_gateway=embeddings,  # type: ignore[arg-type]
        tool_registry=get_tool_registry(),
        parsers=ParserBundle(
            pdf=PdfParser(),
            csv=CsvParser(),
            text=TextParser(),
            chunker=OverlapChunker(),
        ),
        judge_service=JudgeService(llm_gateway=llm),
        critic_optimizer=CriticOptimizerService(llm_gateway=llm, max_iterations=2),
        reporter_service=ReporterService(),
    )


def test_cli_forge_writes_all_seven_artifacts_and_chat_answers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`forge` writes all 7 artifacts unattended and `chat --query` answers from docs."""
    from app import cli

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "leave_policy.md").write_text(
        "# Leave Policy\nShore staff receive 20 days annual leave per calendar year.\n",
        encoding="utf-8",
    )
    (docs_dir / "travel_policy.txt").write_text(
        "Travel expenses require manager approval and receipts within 14 days.\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    brief_file = tmp_path / "brief.txt"
    brief_file.write_text(
        "I need an HR assistant for shore staff covering leave and travel policies.",
        encoding="utf-8",
    )

    fake_llm = _FakeLLMGateway()
    fake_embeddings = _FakeEmbeddingGateway()
    mock_container = _build_mock_container(fake_llm, fake_embeddings)

    with patch("app.cli.build_container", return_value=mock_container):
        exit_code = cli.main(
            [
                "forge",
                "--brief",
                str(brief_file),
                "--docs",
                str(docs_dir),
                "--out",
                str(out_dir),
                "--non-interactive",
            ]
        )

    assert exit_code == 0

    expected_files = [
        "requirements_doc.json",
        "groundability_report.json",
        "agent_definition.json",
        "eval_set.json",
        "iteration_logs.json",
        "scorecard.json",
        "honest_report.md",
    ]
    for filename in expected_files:
        artifact = out_dir / filename
        assert artifact.exists(), f"Missing artifact: {filename}"
        assert artifact.stat().st_size > 0, f"Empty artifact: {filename}"

    eval_data = json.loads((out_dir / "eval_set.json").read_text(encoding="utf-8"))
    assert len(eval_data) >= 20

    agent_data = json.loads((out_dir / "agent_definition.json").read_text(encoding="utf-8"))
    assert "system_prompt" in agent_data
    assert "retrieval_config" in agent_data

    scorecard_data = json.loads((out_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert "final_pass_rate" in scorecard_data

    report_md = (out_dir / "honest_report.md").read_text(encoding="utf-8")
    assert "Pass Rate" in report_md or "pass rate" in report_md.lower()

    capsys.readouterr()

    with patch("app.cli.build_container", return_value=mock_container):
        chat_exit = cli.main(
            [
                "chat",
                "--agent",
                str(out_dir / "agent_definition.json"),
                "--docs",
                str(docs_dir),
                "--query",
                "How many days of annual leave do shore staff receive?",
            ]
        )

    assert chat_exit == 0
    captured = capsys.readouterr()
    assert "20 days annual leave" in captured.out

    last_user_prompt = fake_llm.calls[-1]["messages"][-1]["content"]
    assert "leave_policy.md" in last_user_prompt


def test_cli_forge_with_answers_file_and_interactive_chat(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`forge` accepts inline brief + --answers JSON and `chat` runs interactive stdin loop."""
    from app import cli

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "leave_policy.md").write_text(
        "Shore staff receive 20 days annual leave per calendar year.\n",
        encoding="utf-8",
    )

    answers_file = tmp_path / "answers.json"
    answers_file.write_text(
        json.dumps(["Yes, cite policy filenames.", "Global shore staff."]),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    fake_llm = _FakeLLMGateway()
    fake_embeddings = _FakeEmbeddingGateway()
    mock_container = _build_mock_container(fake_llm, fake_embeddings)

    with patch("app.cli.build_container", return_value=mock_container):
        exit_code = cli.main(
            [
                "forge",
                "--brief",
                "I need an HR policy assistant for shore staff.",
                "--docs",
                str(docs_dir),
                "--out",
                str(out_dir),
                "--answers",
                str(answers_file),
            ]
        )

    assert exit_code == 0
    req_data = json.loads((out_dir / "requirements_doc.json").read_text(encoding="utf-8"))
    assert req_data["clarifying_qa"][0]["answer"] == "Yes, cite policy filenames."

    capsys.readouterr()
    inputs = iter(["What is the leave policy?", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    with patch("app.cli.build_container", return_value=mock_container):
        chat_exit = cli.main(
            [
                "chat",
                "--agent",
                str(out_dir / "agent_definition.json"),
                "--docs",
                str(docs_dir),
            ]
        )

    assert chat_exit == 0
    captured = capsys.readouterr()
    assert "20 days annual leave" in captured.out
