"""Configurable real model catalogue and mock-only demo choices."""

THINKING_EFFORTS = ("low", "medium", "high")

MODEL_OPTIONS = (
    {
        "key": "openai-gpt-5-6-luna",
        "provider": "openai",
        "provider_label": "OpenAI",
        "name": "GPT-5.6 Luna · OpenAI",
        "tier": "Low cost",
        "request_cost_credits": 1,
        "supports_images": True,
        "supports_thinking_effort": True,
        "upstream_model_id": "gpt-5.6-luna",
    },
    {
        "key": "anthropic-claude-haiku-4-5",
        "provider": "anthropic",
        "provider_label": "Anthropic",
        "name": "Claude Haiku 4.5 · Anthropic",
        "tier": "Mid-range",
        "request_cost_credits": 3,
        "supports_images": True,
        "supports_thinking_effort": False,
        "upstream_model_id": "claude-haiku-4-5-20251001",
    },
    {
        "key": "google-gemini-3-8-flash",
        "provider": "google",
        "provider_label": "Google",
        "name": "Gemini 3.8 Flash · Google",
        "tier": "Premium",
        "request_cost_credits": 5,
        "supports_images": True,
        "supports_thinking_effort": True,
        "upstream_model_id": "gemini-3.8-flash",
    },
    {
        "key": "mock-openai-text-only",
        "provider": "openai",
        "provider_label": "OpenAI",
        "name": "OpenAI text-only demo · Mock",
        "tier": "Text-only mock",
        "request_cost_credits": 1,
        "supports_images": False,
        "supports_thinking_effort": False,
        "upstream_model_id": None,
    },
    {
        "key": "mock-openai-vision",
        "provider": "openai",
        "provider_label": "OpenAI",
        "name": "OpenAI image demo · Mock",
        "tier": "Image-capable mock",
        "request_cost_credits": 3,
        "upstream_model_id": None,
        "supports_thinking_effort": False,
        "supports_images": True,
    },
)


def get_model_option(key):
    return next((option for option in MODEL_OPTIONS if option["key"] == key), None)


def get_model_options(mode):
    if mode == "litechat":
        return tuple(option for option in MODEL_OPTIONS if option["upstream_model_id"])
    return MODEL_OPTIONS
