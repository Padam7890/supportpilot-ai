"""Policy for gradually migrating conversation interpretation to an LLM.

Business actions remain authorized by deterministic application services.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationInterpretationPolicy:
    model_first: bool
    deterministic_action_guard: bool = True
    max_history_turns: int = 6
    max_message_characters: int = 1200

    def should_use_model(
        self,
        *,
        risk_level: str,
        negated_action: bool,
        needs_clarification: bool,
        legacy_router_would_invoke: bool,
        semantic_signal: bool = False,
    ) -> bool:
        if not settings.ai_intent_router_enabled:
            return False
        # A deterministic negation signal is only a reason to ask the shared
        # interpreter; it is never itself the final semantic decision.
        if negated_action:
            return True
        if semantic_signal:
            return True
        if needs_clarification:
            return False
        if self.model_first and risk_level != "high":
            return True
        return legacy_router_would_invoke
