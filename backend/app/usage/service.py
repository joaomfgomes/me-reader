"""Registo de consumo de voz e do tutor, e tetos mensais."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.usage.models import UsageEvent

TTS = "tts"
LLM = "llm"


def month_start(now: datetime | None = None) -> datetime:
    """Primeiro instante do mês corrente, em UTC."""
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def estimate_tts_cost(characters: int, settings: Settings) -> float:
    return characters * settings.tts_usd_per_million_chars / 1_000_000


def tts_characters_this_month(session: Session) -> int:
    """Caracteres realmente enviados ao serviço de voz este mês (sem contar a cache)."""
    total = session.scalar(
        select(func.coalesce(func.sum(UsageEvent.characters), 0)).where(
            UsageEvent.kind == TTS,
            UsageEvent.cache_hit.is_(False),
            UsageEvent.created_at >= month_start(),
        )
    )
    return int(total or 0)


def record_tts_usage(
    session: Session,
    settings: Settings,
    *,
    provider: str,
    document_id: int,
    characters: int,
    cache_hit: bool,
) -> None:
    """Acrescenta um evento à sessão. Quem chama é que faz o commit."""
    session.add(
        UsageEvent(
            kind=TTS,
            provider=provider,
            document_id=document_id,
            characters=characters,
            cache_hit=cache_hit,
            # Um acerto de cache não custa nada.
            estimated_cost_usd=0.0 if cache_hit else estimate_tts_cost(characters, settings),
        )
    )


@dataclass(frozen=True)
class TtsUsageSummary:
    month: str
    requests: int
    cache_hits: int
    characters_synthesized: int
    characters_from_cache: int
    estimated_cost_usd: float
    monthly_character_limit: int

    @property
    def cache_hit_rate(self) -> float | None:
        return self.cache_hits / self.requests if self.requests else None

    @property
    def characters_remaining(self) -> int:
        return max(0, self.monthly_character_limit - self.characters_synthesized)


def get_tts_usage_summary(session: Session, settings: Settings) -> TtsUsageSummary:
    start = month_start()
    hit = UsageEvent.cache_hit.is_(True)
    # Uma só consulta com somas condicionais: "case" escolhe, linha a linha,
    # o que entra em cada soma. É SQL normal, igual em SQLite e em Postgres.
    row = session.execute(
        select(
            func.count(UsageEvent.id),
            func.coalesce(func.sum(case((hit, 1), else_=0)), 0),
            func.coalesce(func.sum(case((hit, 0), else_=UsageEvent.characters)), 0),
            func.coalesce(func.sum(case((hit, UsageEvent.characters), else_=0)), 0),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0.0),
        ).where(UsageEvent.kind == TTS, UsageEvent.created_at >= start)
    ).one()
    requests, cache_hits, synthesized, from_cache, cost = row
    return TtsUsageSummary(
        month=start.strftime("%Y-%m"),
        requests=int(requests),
        cache_hits=int(cache_hits),
        characters_synthesized=int(synthesized),
        characters_from_cache=int(from_cache),
        estimated_cost_usd=float(cost),
        monthly_character_limit=settings.monthly_tts_char_limit,
    )


# --- Tutor ------------------------------------------------------------------


def estimate_llm_cost(input_tokens: int, output_tokens: int, settings: Settings) -> float:
    return (
        input_tokens * settings.llm_input_usd_per_million_tokens
        + output_tokens * settings.llm_output_usd_per_million_tokens
    ) / 1_000_000


def llm_cost_this_month(session: Session) -> float:
    """Custo estimado das chamadas ao tutor este mês."""
    total = session.scalar(
        select(func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0.0)).where(
            UsageEvent.kind == LLM, UsageEvent.created_at >= month_start()
        )
    )
    return float(total or 0.0)


def record_llm_usage(
    session: Session,
    settings: Settings,
    *,
    provider: str,
    document_id: int,
    characters: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_hit: bool,
) -> None:
    """Acrescenta um evento do tutor à sessão. Quem chama é que faz o commit."""
    session.add(
        UsageEvent(
            kind=LLM,
            provider=provider,
            document_id=document_id,
            characters=characters,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=cache_hit,
            estimated_cost_usd=0.0
            if cache_hit
            else estimate_llm_cost(input_tokens, output_tokens, settings),
        )
    )


@dataclass(frozen=True)
class LlmUsageSummary:
    requests: int
    cache_hits: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    monthly_usd_limit: float

    @property
    def cache_hit_rate(self) -> float | None:
        return self.cache_hits / self.requests if self.requests else None

    @property
    def usd_remaining(self) -> float:
        return max(0.0, self.monthly_usd_limit - self.estimated_cost_usd)


def get_llm_usage_summary(session: Session, settings: Settings) -> LlmUsageSummary:
    hit = UsageEvent.cache_hit.is_(True)
    row = session.execute(
        select(
            func.count(UsageEvent.id),
            func.coalesce(func.sum(case((hit, 1), else_=0)), 0),
            func.coalesce(func.sum(UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(UsageEvent.output_tokens), 0),
            func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0.0),
        ).where(UsageEvent.kind == LLM, UsageEvent.created_at >= month_start())
    ).one()
    requests, cache_hits, input_tokens, output_tokens, cost = row
    return LlmUsageSummary(
        requests=int(requests),
        cache_hits=int(cache_hits),
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        estimated_cost_usd=float(cost),
        monthly_usd_limit=settings.monthly_llm_usd_limit,
    )
