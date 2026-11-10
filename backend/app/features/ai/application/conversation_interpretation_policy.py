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
    ) -> bool:
        if negated_action or needs_clarification:
            return False
        if self.model_first and risk_level != "high":
            return True
        return legacy_router_would_invoke
