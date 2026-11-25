"""Application Dependency Injection Container."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.application.services.critic_optimizer import CriticOptimizerService
from app.application.services.judge_service import JudgeService
from app.application.services.reporter_service import ReporterService
from app.config import Settings, get_settings
from app.infrastructure.cache.ttl_cache import InMemoryTTLCache
from app.infrastructure.llm.embeddings import CloudflareEmbeddingsAdapter
from app.infrastructure.llm.litellm_adapter import LiteLLMAdapter
from app.infrastructure.parsers import CsvParser, OverlapChunker, PdfParser, TextParser
from app.infrastructure.tools.registry import ToolRegistry, get_tool_registry


@dataclass(slots=True)
class ParserBundle:
    """Collection of document parsers and chunker."""

    pdf: PdfParser
    csv: CsvParser
    text: TextParser
    chunker: OverlapChunker


@dataclass(slots=True)
class AppContainer:
    """Root DI container wiring infrastructure adapters and application services."""

    settings: Settings
    cache: InMemoryTTLCache
    llm_gateway: LiteLLMAdapter
    embedding_gateway: CloudflareEmbeddingsAdapter
    tool_registry: ToolRegistry
    parsers: ParserBundle
    judge_service: JudgeService
    critic_optimizer: CriticOptimizerService
    reporter_service: ReporterService


@lru_cache(maxsize=1)
def build_container() -> AppContainer:
    """Build and cache the singleton AppContainer from Settings."""
    settings = get_settings()
    cache = InMemoryTTLCache(
        maxsize=1024,
        default_ttl_seconds=max(1, settings.forge_cache_ttl_seconds),
    )
    llm_gateway = LiteLLMAdapter(
        litellm_base_url=settings.litellm_base_url,
        api_key=settings.litellm_master_key or None,
    )
    embedding_gateway = CloudflareEmbeddingsAdapter(
        account_id=settings.cloudflare_account_id,
        api_token=settings.cloudflare_api_token,
    )
    tool_registry = get_tool_registry()
    parsers = ParserBundle(
        pdf=PdfParser(),
        csv=CsvParser(),
        text=TextParser(),
        chunker=OverlapChunker(),
    )
    judge_service = JudgeService(
        llm_gateway=llm_gateway,
        judge_tier="fast-judge",
        agent_model="orchestrator-primary",
    )
    critic_optimizer = CriticOptimizerService(
        llm_gateway=llm_gateway,
        critic_tier="orchestrator-primary",
        max_iterations=settings.forge_max_iterations,
        min_delta=settings.forge_early_stop_min_delta,
    )
    reporter_service = ReporterService()

    return AppContainer(
        settings=settings,
        cache=cache,
        llm_gateway=llm_gateway,
        embedding_gateway=embedding_gateway,
        tool_registry=tool_registry,
        parsers=parsers,
        judge_service=judge_service,
        critic_optimizer=critic_optimizer,
        reporter_service=reporter_service,
    )
