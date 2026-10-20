"""MiniMax text preset, request serialization, and saved-selection regressions."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from acestep.text_tasks.external_ai_request_helpers import (
    build_planning_messages,
    build_request_for_protocol,
)
from acestep.text_tasks.external_lm_model_discovery import discover_external_models
from acestep.text_tasks.external_lm_providers import (
    build_external_model_choice,
    get_external_provider_profile,
)
from acestep.text_tasks.external_lm_runtime_store import (
    load_external_lm_runtime_settings,
)


class MiniMaxTextCompatibilityTests(unittest.TestCase):
    """Exercise the existing public helpers without requiring an inference client."""

    @patch("acestep.text_tasks.external_lm_model_discovery.request.urlopen")
    def test_official_presets_offer_flash_then_m3_without_discovery_http(self, urlopen) -> None:
        """Both protocols and regions expose the same maintained model choices."""

        for provider in ("minimax", "minimax_anthropic"):
            profile = get_external_provider_profile(provider)
            self.assertEqual(profile.default_model, "MiniMax-M3.1-Flash")
            self.assertEqual(
                build_external_model_choice(provider, ""),
                f"external:{provider}:MiniMax-M3.1-Flash",
            )
            for region, endpoint in profile.base_url_presets:
                with self.subTest(provider=provider, region=region):
                    models = discover_external_models(
                        provider=provider,
                        protocol=profile.protocol,
                        base_url=endpoint + "/",
                        api_key="test-key",
                    )
                    self.assertEqual(models, ["MiniMax-M3.1-Flash", "MiniMax-M3"])
        urlopen.assert_not_called()

    def test_serialized_requests_preserve_model_protocol_and_token_limit(self) -> None:
        """Serialize real helper output for both models, protocols, and regions."""

        for provider in ("minimax", "minimax_anthropic"):
            profile = get_external_provider_profile(provider)
            for region, endpoint in profile.base_url_presets:
                for model in ("MiniMax-M3.1-Flash", "MiniMax-M3"):
                    with self.subTest(provider=provider, region=region, model=model):
                        payload, headers = build_request_for_protocol(
                            protocol=profile.protocol,
                            provider=provider,
                            api_key="test-key",
                            model=model,
                            messages=build_planning_messages("Gentle acoustic instrumental"),
                            base_url=endpoint,
                            max_tokens=768,
                            disable_thinking=True,
                            require_json_output=True,
                        )
                        wire = json.loads(json.dumps(payload).encode("utf-8"))
                        self.assertEqual(wire["model"], model)
                        self.assertEqual(wire["max_tokens"], 768)
                        self.assertNotIn("thinking", wire)
                        self.assertNotIn("reasoning_effort", wire)
                        self.assertNotIn("output_config", wire)
                        self.assertNotIn("tools", wire)
                        self.assertNotIn("stream", wire)
                        self.assertEqual(headers["Content-Type"], "application/json")
                        if profile.protocol == "anthropic_messages":
                            self.assertEqual(headers["x-api-key"], "test-key")
                            self.assertEqual(headers["anthropic-version"], "2023-06-01")
                            self.assertEqual(wire["messages"][0]["role"], "user")
                            self.assertIn("system", wire)
                            self.assertNotIn("response_format", wire)
                        else:
                            self.assertEqual(headers["Authorization"], "Bearer test-key")
                            self.assertEqual(wire["messages"][0]["role"], "system")
                            self.assertEqual(wire["response_format"], {"type": "json_object"})

    @patch("acestep.text_tasks.external_lm_runtime_store.load_all_external_lm_runtime_settings")
    def test_explicit_saved_models_are_not_replaced(self, load_settings) -> None:
        """Legacy and custom saved selections remain valid compatibility choices."""

        for provider in ("minimax", "minimax_anthropic"):
            profile = get_external_provider_profile(provider)
            for model in ("MiniMax-M3", "MiniMax-M2.7", "private-model-alias"):
                with self.subTest(provider=provider, model=model):
                    settings = {
                        "provider": provider,
                        "protocol": profile.protocol,
                        "model": model,
                        "base_url": "https://gateway.example.invalid/custom",
                    }
                    load_settings.return_value = {
                        "active_provider": provider,
                        "providers": {provider: settings},
                    }
                    self.assertEqual(load_external_lm_runtime_settings(provider), settings)
                    self.assertEqual(
                        build_external_model_choice(provider, model),
                        f"external:{provider}:{model}",
                    )

    @patch("acestep.text_tasks.external_lm_model_discovery.request.urlopen")
    def test_custom_endpoint_discovery_keeps_gateway_models_and_auth(self, urlopen) -> None:
        """The maintained catalog does not override custom gateways' model lists."""

        urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"data": [{"id": "private-model-alias"}]}'
        )
        for provider in ("minimax", "minimax_anthropic"):
            profile = get_external_provider_profile(provider)
            with self.subTest(provider=provider):
                models = discover_external_models(
                    provider=provider,
                    protocol=profile.protocol,
                    base_url="https://gateway.example.invalid/v1",
                    api_key="test-key",
                )
                self.assertEqual(models, ["private-model-alias"])
                request = urlopen.call_args.args[0]
                self.assertEqual(request.full_url, "https://gateway.example.invalid/v1/models")
                self.assertEqual(request.get_method(), "GET")
                if profile.protocol == "anthropic_messages":
                    self.assertEqual(request.get_header("X-api-key"), "test-key")
                else:
                    self.assertEqual(request.get_header("Authorization"), "Bearer test-key")


if __name__ == "__main__":
    unittest.main()
