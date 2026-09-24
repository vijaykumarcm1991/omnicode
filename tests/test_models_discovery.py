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
    assert "raw" in models[0]



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


def test_models_pagination_and_filtering():
    from omnicode.ui.model_browser import filter_models, build_models_table

    # Generate 45 mock models
    mock_models = [
        {"id": f"model-variant-{i}", "owned_by": "org-a" if i % 2 == 0 else "org-b", "raw": {}}
        for i in range(1, 46)
    ]

    # Test filtering
    filtered = filter_models(mock_models, "variant-1")
    # Matches variant-1, variant-10..19 (11 models)
    assert len(filtered) == 11

    # Test pagination (15 per page -> 3 pages)
    table_p1, total_pages, total_count = build_models_table(mock_models, page=1, page_size=15)
    assert total_pages == 3
    assert total_count == 45
    assert len(table_p1.rows) == 15

    # Page 3 should contain remaining 15 items
    table_p3, _, _ = build_models_table(mock_models, page=3, page_size=15)
    assert len(table_p3.rows) == 15

    # Page beyond bounds clamps to last page
    table_p99, _, _ = build_models_table(mock_models, page=99, page_size=15)
    assert len(table_p99.rows) == 15

