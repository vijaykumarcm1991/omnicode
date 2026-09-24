"""
Token tracking and cost estimation utility for OmniCode.
Estimates tokens using tiktoken (fallback to character heuristics) and tracks session usage.
"""

from typing import Dict, Any, Optional
import tiktoken

# Pricing per million tokens (approximate USD)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o1": {"input": 15.00, "output": 60.00},
    "o3-mini": {"input": 1.10, "output": 4.40},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Anthropic via OpenRouter
    "anthropic/claude-3.7-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3.5-haiku": {"input": 0.80, "output": 4.00},
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "deepseek/deepseek-r1": {"input": 0.55, "output": 2.19},
    "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    # Groq / Llama
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
}


class TokenTracker:
    """Tracks token consumption, session totals, and estimated costs."""

    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.session_prompt_tokens: int = 0
        self.session_completion_tokens: int = 0
        self.last_turn_prompt_tokens: int = 0
        self.last_turn_completion_tokens: int = 0
        self._encoder: Optional[Any] = None
        self._init_encoder()

    def _init_encoder(self):
        try:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._encoder = None

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        if not text:
            return 0
        if self._encoder:
            try:
                return len(self._encoder.encode(text, disallowed_special=()))
            except Exception:
                pass
        # Fallback estimation: ~4 chars per token
        return max(1, len(text) // 4)

    def estimate_messages_tokens(self, messages: list) -> int:
        """Estimate total tokens across a conversation messages list."""
        total = 0
        for msg in messages:
            total += 4  # message overhead
            content = msg.get("content")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.estimate_tokens(part["text"])
            # Tool calls
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    total += 10
                    fn = tc.get("function", {})
                    total += self.estimate_tokens(fn.get("name", ""))
                    total += self.estimate_tokens(fn.get("arguments", ""))
        total += 2  # priming
        return total

    def record_usage(self, prompt_tokens: int, completion_tokens: int):
        """Record usage from an API response."""
        self.last_turn_prompt_tokens = prompt_tokens
        self.last_turn_completion_tokens = completion_tokens
        self.session_prompt_tokens += prompt_tokens
        self.session_completion_tokens += completion_tokens

    def get_estimated_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated cost in USD for given token usage."""
        pricing = None
        # Exact match
        if self.model_name in MODEL_PRICING:
            pricing = MODEL_PRICING[self.model_name]
        else:
            # Fuzzy match
            for m, p in MODEL_PRICING.items():
                if m in self.model_name or self.model_name in m:
                    pricing = p
                    break
        if not pricing:
            # Default to gpt-4o pricing
            pricing = MODEL_PRICING["gpt-4o"]

        cost = (prompt_tokens / 1_000_000 * pricing["input"]) + (
            completion_tokens / 1_000_000 * pricing["output"]
        )
        return cost

    def get_session_cost(self) -> float:
        return self.get_estimated_cost(
            self.session_prompt_tokens, self.session_completion_tokens
        )

    def get_summary(self) -> Dict[str, Any]:
        """Return token and cost statistics summary."""
        return {
            "model": self.model_name,
            "session_prompt_tokens": self.session_prompt_tokens,
            "session_completion_tokens": self.session_completion_tokens,
            "session_total_tokens": self.session_prompt_tokens
            + self.session_completion_tokens,
            "session_cost_usd": self.get_session_cost(),
            "last_turn_prompt_tokens": self.last_turn_prompt_tokens,
            "last_turn_completion_tokens": self.last_turn_completion_tokens,
        }
