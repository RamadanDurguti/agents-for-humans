"""Pick a model provider from the environment.

Strands is provider-agnostic, so Ratchet is too. This exists so that the same
agent runs on Bedrock in a demo account and on a laptop with Ollama and no
account at all — which matters, because the people this tool is for are not
going to open an AWS console.
"""
from __future__ import annotations

import os


def build_model():
    """Return a Strands model instance chosen by RATCHET_PROVIDER.

    bedrock (default) | ollama | openai | anthropic
    Returning None hands control back to the SDK's own default.
    """
    provider = os.environ.get("RATCHET_PROVIDER", "bedrock").strip().lower()

    if provider == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(
            host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            model_id=os.environ.get("RATCHET_MODEL", "llama3.1"),
            temperature=0.2,
        )

    if provider == "openai":
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            client_args={"api_key": os.environ["OPENAI_API_KEY"]},
            model_id=os.environ.get("RATCHET_MODEL", "gpt-4o-mini"),
        )

    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel

        return AnthropicModel(
            client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
            model_id=os.environ.get("RATCHET_MODEL", "claude-sonnet-4-5"),
            max_tokens=2048,
        )

    from strands.models import BedrockModel

    return BedrockModel(
        model_id=os.environ.get("RATCHET_MODEL", "global.anthropic.claude-sonnet-4-6"),
        region_name=os.environ.get("AWS_REGION", "us-west-2"),
        temperature=0.2,
    )
