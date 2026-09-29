"""Configurable mock catalogue. These are internal keys, not upstream model IDs."""

MODEL_OPTIONS = (
    {
        "key": "mock-openai-low",
        "provider": "openai",
        "provider_label": "OpenAI",
        "name": "OpenAI target · Low cost",
        "tier": "Low cost",
        "request_cost_credits": 1,
        "supports_images": False,
        "upstream_model_id": None,
    },
    {
        "key": "mock-anthropic-mid",
        "provider": "anthropic",
        "provider_label": "Anthropic",
        "name": "Anthropic target · Mid-range",
        "tier": "Mid-range",
        "request_cost_credits": 3,
        "supports_images": False,
        "upstream_model_id": None,
    },
    {
        "key": "mock-google-premium",
        "provider": "google",
        "provider_label": "Google",
        "name": "Google target · Premium",
        "tier": "Premium",
        "request_cost_credits": 5,
        "supports_images": False,
        "upstream_model_id": None,
    },
    {
        "key": "mock-openai-vision",
        "provider": "openai",
        "provider_label": "OpenAI",
        "name": "OpenAI target · Image demo",
        "tier": "Image-capable mock",
        "request_cost_credits": 3,
        "supports_images": True,
        "upstream_model_id": None,
    },
)


def get_model_option(key):
    return next((option for option in MODEL_OPTIONS if option["key"] == key), None)
