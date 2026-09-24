"""
Async OpenAI-compatible LLM client for OmniCode.
Streams content, reasoning tokens (<think> / reasoning_content), and tool calls.
Supports custom base_url, API keys, headers, and retry logic.
"""

import json
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
import httpx
import openai
from openai import AsyncOpenAI
from ..config import OmniConfig


class StreamChunk:
    """Represents an incremental streaming event from the model."""

    def __init__(
        self,
        content: str = "",
        reasoning: str = "",
        tool_call_delta: Optional[Dict[str, Any]] = None,
        is_done: bool = False,
    ):
        self.content = content
        self.reasoning = reasoning
        self.tool_call_delta = tool_call_delta
        self.is_done = is_done


class LLMResponse:
    """Aggregated final response from a model turn."""

    def __init__(
        self,
        content: str = "",
        reasoning: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ):
        self.content = content
        self.reasoning = reasoning
        self.tool_calls = tool_calls or []
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class LLMClient:
    """OpenAI API compatible asynchronous LLM client with idle-resilient transport."""

    def __init__(self, config: OmniConfig):
        self.config = config
        self._http_client: Optional[httpx.AsyncClient] = None
        self.client: AsyncOpenAI = self._create_client()

    def _create_client(self) -> AsyncOpenAI:
        """Create a resilient AsyncOpenAI client with short keepalive expiry to prevent stale sockets."""
        api_key = self.config.api_key.strip() if self.config.api_key else "EMPTY"
        
        # Explicit connection pool limits with short keepalive expiry
        # This prevents hangs when middleboxes or servers close idle TCP connections
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=20,
                keepalive_expiry=15.0,  # drop idle sockets after 15 seconds
            ),
            timeout=httpx.Timeout(
                timeout=120.0,
                connect=15.0,
                read=120.0,
                write=30.0,
                pool=10.0,
            ),
            headers=self.config.custom_headers or None,
        )

        return AsyncOpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
            http_client=self._http_client,
            max_retries=2,
        )

    def reconnect(self):
        """Re-create client and fresh connection pool after idle periods or connection drops."""
        try:
            if self._http_client and not self._http_client.is_closed:
                # Close old transport without blocking
                pass
        except Exception:
            pass
        self.client = self._create_client()

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream chat completions from OpenAI-compatible endpoint with automatic reconnect on idle."""
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if self.config.max_tokens:
            kwargs["max_tokens"] = self.config.max_tokens

        stream = None
        # Attempt request with automatic reconnection if idle socket died
        for attempt in range(2):
            try:
                stream = await self.client.chat.completions.create(**kwargs)
                break
            except (
                openai.APIConnectionError,
                openai.APITimeoutError,
                httpx.RemoteProtocolError,
                httpx.ReadError,
                httpx.ConnectError,
                httpx.PoolTimeout,
            ) as e:
                if attempt == 0:
                    # Stale connection from idle state: refresh client and retry once
                    self.reconnect()
                    continue
                raise RuntimeError(
                    f"Connection Error: Could not connect to LLM server at {self.config.base_url} after retry. "
                    f"Verify your network connection or server status. ({str(e)})"
                )
            except openai.AuthenticationError as e:
                raise RuntimeError(
                    f"Authentication Error with {self.config.base_url}: Invalid or missing API key. "
                    f"Please set your API key using 'omnicode auth' or OPENAI_API_KEY environment variable. ({str(e)})"
                )
            except openai.BadRequestError as e:
                raise RuntimeError(f"Bad Request Error ({self.config.model}): {str(e)}")
            except Exception as e:
                raise RuntimeError(f"LLM API Error: {str(e)}")

        if not stream:
            return

        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                content_delta = getattr(delta, "content", "") or ""
                
                # Check for DeepSeek-R1 reasoning_content or reasoning
                reasoning_delta = ""
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_delta = delta.reasoning_content
                elif hasattr(delta, "reasoning") and delta.reasoning:
                    reasoning_delta = delta.reasoning

                # Check tool calls delta
                tool_calls_delta = getattr(delta, "tool_calls", None)

                yield StreamChunk(
                    content=content_delta,
                    reasoning=reasoning_delta,
                    tool_call_delta=tool_calls_delta,
                    is_done=chunk.choices[0].finish_reason is not None,
                )
        except (openai.APIConnectionError, httpx.RemoteProtocolError, httpx.ReadError) as e:
            self.reconnect()
            raise RuntimeError(f"Connection dropped during streaming: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"LLM Streaming Error: {str(e)}")


    async def complete_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        on_content_chunk=None,
        on_reasoning_chunk=None,
    ) -> LLMResponse:
        """Execute a streaming turn and assemble the complete response and tool calls."""
        accumulated_content = []
        accumulated_reasoning = []
        raw_tool_calls: Dict[int, Dict[str, Any]] = {}

        in_think_tag = False

        async for chunk in self.stream_chat(messages, tools):
            # Stream reasoning content
            if chunk.reasoning:
                accumulated_reasoning.append(chunk.reasoning)
                if on_reasoning_chunk:
                    await on_reasoning_chunk(chunk.reasoning)

            # Stream content
            if chunk.content:
                # Handle models that output <think>...</think> inline in content
                text = chunk.content
                if "<think>" in text:
                    in_think_tag = True
                    parts = text.split("<think>", 1)
                    if parts[0]:
                        accumulated_content.append(parts[0])
                        if on_content_chunk:
                            await on_content_chunk(parts[0])
                    if parts[1]:
                        accumulated_reasoning.append(parts[1])
                        if on_reasoning_chunk:
                            await on_reasoning_chunk(parts[1])
                    continue
                elif "</think>" in text and in_think_tag:
                    in_think_tag = False
                    parts = text.split("</think>", 1)
                    if parts[0]:
                        accumulated_reasoning.append(parts[0])
                        if on_reasoning_chunk:
                            await on_reasoning_chunk(parts[0])
                    if parts[1]:
                        accumulated_content.append(parts[1])
                        if on_content_chunk:
                            await on_content_chunk(parts[1])
                    continue

                if in_think_tag:
                    accumulated_reasoning.append(text)
                    if on_reasoning_chunk:
                        await on_reasoning_chunk(text)
                else:
                    accumulated_content.append(text)
                    if on_content_chunk:
                        await on_content_chunk(text)

            # Stream tool calls
            if chunk.tool_call_delta:
                for tc in chunk.tool_call_delta:
                    idx = tc.index if hasattr(tc, "index") else 0
                    if idx not in raw_tool_calls:
                        raw_tool_calls[idx] = {
                            "id": tc.id if hasattr(tc, "id") and tc.id else f"call_{idx}",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    
                    if hasattr(tc, "id") and tc.id:
                        raw_tool_calls[idx]["id"] = tc.id

                    if hasattr(tc, "function") and tc.function:
                        fn = tc.function
                        if hasattr(fn, "name") and fn.name:
                            raw_tool_calls[idx]["function"]["name"] += fn.name
                        if hasattr(fn, "arguments") and fn.arguments:
                            raw_tool_calls[idx]["function"]["arguments"] += fn.arguments

        full_content = "".join(accumulated_content)
        full_reasoning = "".join(accumulated_reasoning)
        final_tool_calls = list(raw_tool_calls.values()) if raw_tool_calls else []

        return LLMResponse(
            content=full_content,
            reasoning=full_reasoning,
            tool_calls=final_tool_calls if final_tool_calls else None,
        )

    async def list_models(self) -> List[Dict[str, Any]]:
        """Fetch all available models from the /v1/models endpoint of the active base_url."""
        try:
            response = await self.client.models.list()
            models = []
            for item in response.data:
                raw_dict = item.model_dump() if hasattr(item, "model_dump") else getattr(item, "__dict__", {})
                models.append({
                    "id": item.id,
                    "owned_by": getattr(item, "owned_by", "") or "unknown",
                    "created": getattr(item, "created", None),
                    "raw": raw_dict,
                })
            return sorted(models, key=lambda m: m["id"].lower())
        except Exception as e:
            raise RuntimeError(
                f"Failed to discover models from {self.config.base_url}/models: {str(e)}"
            )

