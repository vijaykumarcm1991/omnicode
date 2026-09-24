"""
Unit tests for model discovery via /v1/models endpoint and custom model configurations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from omnicode.config import OmniConfig
from omnicode.core.llm_client import LLMClient


@pytest.mark.asyncio
async def test_discover_models_from_endpoint():
    config = OmniConfig(base_url="http://localhost:11434/v1", model="custom-fine-tuned-v1")
    client = LLMClient(config)

    # Mock the models.list response from OpenAI SDK
    mock_model_1 = MagicMock()
    mock_model_1.id = "custom-fine-tuned-v1"
    mock_model_1.owned_by = "my-org"
    mock_model_1.created = 1700000000

    mock_model_2 = MagicMock()
    mock_model_2.id = "qwen2.5-coder-32b"
    mock_model_2.owned_by = "ollama"
    mock_model_2.created = 1700000000

    mock_response = MagicMock()
    mock_response.data = [mock_model_1, mock_model_2]

    client.client.models.list = AsyncMock(return_value=mock_response)

    models = await client.list_models()
    assert len(models) == 2
    assert models[0]["id"] == "custom-fine-tuned-v1"
    assert models[1]["id"] == "qwen2.5-coder-32b"
    assert models[0]["owned_by"] == "my-org"


def test_custom_model_configuration():
    # Test configuring arbitrary custom model and base_url
    config = OmniConfig(
        base_url="http://192.168.1.100:8000/v1",
        model="custom-internal-coder-70b",
        api_key="custom-secret-key",
        context_window=64000,
        temperature=0.3,
    )
    assert config.base_url == "http://192.168.1.100:8000/v1"
    assert config.model == "custom-internal-coder-70b"
    assert config.context_window == 64000
