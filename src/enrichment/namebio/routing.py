"""
Routing decision: every new domain gets its description from the LLM (the
rule engine is only used to save keywords/tokens and to order the queue), so
nothing is embedded here. The queue drains by priority, highest sale price
first, which matters when the LLM has a daily request cap:

    price >= PREMIUM (10k)      -> premium_domain   (priority 30)
    price >= HIGH_VALUE (5k)    -> high_value       (priority 25)
    confidence < MEDIUM         -> low_confidence   (priority 10)
    otherwise                   -> standard         (priority 5)

Kept dependency-free (just config) so it is trivially unit-testable.
"""

from dataclasses import dataclass
from typing import Optional

import config


@dataclass
class RoutingDecision:
    status: str                 # always 'queued_for_llm'
    queue_reason: Optional[str]
    embed_now: bool             # always False: embedding waits for the LLM description
    enqueue: bool               # always True


def decide(confidence: float, best_price: float) -> RoutingDecision:
    if best_price is not None and best_price >= config.PREMIUM_PRICE_THRESHOLD:
        reason = "premium_domain"
    elif best_price is not None and best_price >= config.HIGH_VALUE_PRICE_THRESHOLD:
        reason = "high_value"
    elif confidence < config.MEDIUM_CONFIDENCE:
        reason = "low_confidence"
    else:
        reason = "standard"
    return RoutingDecision(status="queued_for_llm", queue_reason=reason, embed_now=False, enqueue=True)
