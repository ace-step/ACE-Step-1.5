"""Provider profiles for external LM setup and picker integration."""

from __future__ import annotations

from dataclasses import dataclass

CUSTOM_BASE_URL_PRESET = "__custom__"


@dataclass(frozen=True)
class ExternalProviderProfile:
    """Static configuration for a supported external provider."""

    provider_id: str
    label: str
    protocol: str
    default_model: str
    default_base_url: str
    api_key_env: str
    api_key_required: bool
    secret_path_env: str
    secret_file_name: str
    base_url_presets: tuple[tuple[str, str], ...]


_EXTERNAL_PROVIDER_PROFILES: dict[str, ExternalProviderProfile] = {
    "zai": ExternalProviderProfile(
        provider_id="zai",
        label="Z.ai (GLM)",
        protocol="openai_chat",
        default_model="glm-4.5-flash",
        default_base_url="https://api.z.ai/api/paas/v4/chat/completions",
        api_key_env="ACESTEP_GLM_API_KEY",
        api_key_required=True,
        secret_path_env="ACESTEP_GLM_SECRET_PATH",
        secret_file_name="glm_api_key.enc",
        base_url_presets=(
            ("Standard chat endpoint", "https://api.z.ai/api/paas/v4/chat/completions"),
            ("Coding endpoint", "https://api.z.ai/api/coding/paas/v4/chat/completions"),
        ),
    ),
    "openai": ExternalProviderProfile(
        provider_id="openai",
        label="OpenAI",
        protocol="openai_chat",
        default_model="gpt-4o-mini",
        default_base_url="https://api.openai.com/v1/chat/completions",
        api_key_env="ACESTEP_OPENAI_API_KEY",
        api_key_required=True,
        secret_path_env="ACESTEP_OPENAI_SECRET_PATH",
        secret_file_name="openai_api_key.enc",
        base_url_presets=(
            ("OpenAI chat completions", "https://api.openai.com/v1/chat/completions"),
        ),
    ),
    "claude": ExternalProviderProfile(
        provider_id="claude",
        label="Anthropic Claude",
        protocol="anthropic_messages",
        default_model="claude-3-7-sonnet-latest",
        default_base_url="https://api.anthropic.com/v1/messages",
        api_key_env="ACESTEP_ANTHROPIC_API_KEY",
        api_key_required=True,
        secret_path_env="ACESTEP_ANTHROPIC_SECRET_PATH",
        secret_file_name="anthropic_api_key.enc",
        base_url_presets=(
            ("Anthropic messages", "https://api.anthropic.com/v1/messages"),
        ),
    ),
    "ollama": ExternalProviderProfile(
        provider_id="ollama",
        label="Ollama",
        protocol="openai_chat",
        default_model="qwen3:4b",
        default_base_url="http://127.0.0.1:11434/v1/chat/completions",
        api_key_env="ACESTEP_OLLAMA_API_KEY",
        api_key_required=False,
        secret_path_env="ACESTEP_OLLAMA_SECRET_PATH",
        secret_file_name="ollama_api_key.enc",
        base_url_presets=(
            ("Local Ollama", "http://127.0.0.1:11434/v1/chat/completions"),
            ("Localhost alias", "http://localhost:11434/v1/chat/completions"),
        ),
    ),
}


def get_external_provider_profile(provider: str | None) -> ExternalProviderProfile:
    """Return the provider profile for a provider identifier.

    Raises:
        ValueError: If ``provider`` is not a supported external provider.
    """

    token = (provider or "").strip().lower()
    if token in _EXTERNAL_PROVIDER_PROFILES:
        return _EXTERNAL_PROVIDER_PROFILES[token]
    raise ValueError(f"Unsupported external provider: {provider!r}")


def get_external_provider_choices() -> list[tuple[str, str]]:
    """Return provider dropdown choices as ``(label, value)`` pairs."""

    order = ("zai", "openai", "claude", "ollama")
    return [
        (_EXTERNAL_PROVIDER_PROFILES[provider_id].label, provider_id)
        for provider_id in order
    ]


def build_external_model_choice(provider: str, model: str) -> str:
    """Build the LM dropdown token for an external provider/model pair.

    The returned token uses ``external:{provider_id}:{model}``, where the
    provider id is the canonical split point for downstream parsing.
    """

    profile = get_external_provider_profile(provider)
    normalized_model = (model or "").strip() or profile.default_model
    return f"external:{profile.provider_id}:{normalized_model}"


def get_external_base_url_preset_choices(provider: str | None) -> list[tuple[str, str]]:
    """Return user-facing base-URL preset choices for a provider."""

    profile = get_external_provider_profile(provider)
    return [*profile.base_url_presets, ("Custom", CUSTOM_BASE_URL_PRESET)]


def get_external_base_url_preset_value(provider: str | None, base_url: str | None) -> str:
    """Return the matching preset value for a base URL, or the custom preset token."""

    profile = get_external_provider_profile(provider)
    normalized_base_url = (base_url or "").strip()
    for _, preset_value in profile.base_url_presets:
        if preset_value == normalized_base_url:
            return preset_value
    return CUSTOM_BASE_URL_PRESET
