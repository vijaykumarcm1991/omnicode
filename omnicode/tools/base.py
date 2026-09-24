"""
Base tool interface and result schema for OmniCode agent tools.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Standard execution result from an agent tool."""

    success: bool = True
    output: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_message_content(self) -> str:
        """Format the result as content string for LLM tool response."""
        if not self.success:
            err = self.error or "Unknown error"
            if self.output:
                return f"Error: {err}\nOutput: {self.output}"
            return f"Error: {err}"
        return self.output


class BaseTool(ABC):
    """Abstract base class for all OmniCode agent tools."""

    name: str
    description: str
    is_read_only: bool = False

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for the tool's parameters."""
        pass

    def to_openai_tool(self) -> Dict[str, Any]:
        """Format tool definition for OpenAI function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool asynchronously with provided arguments."""
        pass
