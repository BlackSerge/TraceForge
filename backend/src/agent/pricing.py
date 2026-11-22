"""Cost of an LLM call from its token usage.

Cost is never guessed. Three outcomes:
- the price comes from settings (LLM_PRICE_INPUT_PER_MTOK / LLM_PRICE_OUTPUT_PER_MTOK) -> real cost;
- the model is a known free-tier model -> 0, flagged as free tier (reports must not read it as
  "this agent is cheap": the zero is a billing fact, not a measurement);
- unknown model without configured prices -> None (cost unknown).
"""
from dataclasses import dataclass
from decimal import Decimal

from src.config import settings

# Models used without billing during development. Prefix match on the model name.
FREE_TIER_MODELS = ("gemini-3.1-flash-lite",)


@dataclass(frozen=True)
class Price:
    input_per_mtok: Decimal  # USD per 1M input tokens
    output_per_mtok: Decimal  # USD per 1M output tokens
    free_tier: bool = False


def price_for(model: str | None) -> Price | None:
    if settings.llm_price_input_per_mtok is not None and settings.llm_price_output_per_mtok is not None:
        return Price(Decimal(str(settings.llm_price_input_per_mtok)), Decimal(str(settings.llm_price_output_per_mtok)))
    name = model or settings.llm_model
    if any(name.startswith(m) for m in FREE_TIER_MODELS):
        return Price(Decimal(0), Decimal(0), free_tier=True)
    return None


def cost_for(model: str | None, tokens_in: int | None, tokens_out: int | None) -> Decimal | None:
    """USD cost of one call, or None when the price or the token usage is unknown."""
    price = price_for(model)
    if price is None or tokens_in is None or tokens_out is None:
        return None
    return (price.input_per_mtok * tokens_in + price.output_per_mtok * tokens_out) / Decimal(1_000_000)


def is_free_tier(model: str | None) -> bool:
    price = price_for(model)
    return price is not None and price.free_tier
