"""Deep Agent context configuration built on top of BaseContext."""

from dataclasses import dataclass, field
from typing import Annotated

from yunesa.agents import BaseContext

from .prompt import DEEP_PROMPT


@dataclass
class DeepContext(BaseContext):
    """Context settings used by the deep analysis agent."""

    # System prompt used by the deep analysis workflow.
    system_prompt: Annotated[str, {"__template_metadata__": {"kind": "prompt"}}] = field(
        default=DEEP_PROMPT,
        metadata={"name": "System Prompt", "description": "Role and behavior guidance for the deep agent."},
    )

    subagents_model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default="groq/qwen/qwen3.8-27b",
        metadata={
            "name": "Sub-agent Model",
            "description": "Default model for sub-agents; individual sub-agent configuration can override it.",
        },
    )
