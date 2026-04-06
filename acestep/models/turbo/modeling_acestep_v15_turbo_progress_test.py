import unittest

import torch

from acestep.models.turbo.modeling_acestep_v15_turbo import AceStepConditionGenerationModel


class _FakeDecoder:
    def __call__(
        self,
        hidden_states,
        timestep,
        timestep_r,
        attention_mask,
        encoder_hidden_states,
        encoder_attention_mask,
        context_latents,
        use_cache,
        past_key_values,
    ):
        _ = timestep
        _ = timestep_r
        _ = attention_mask
        _ = encoder_hidden_states
        _ = encoder_attention_mask
        _ = context_latents
        _ = use_cache
        return torch.zeros_like(hidden_states), past_key_values


class _FakeTurboHost:
    def __init__(self):
        self.decoder = _FakeDecoder()

    def prepare_condition(self, **kwargs):
        src_latents = kwargs["src_latents"]
        attention_mask = kwargs["attention_mask"]
        return src_latents, attention_mask, src_latents

    def prepare_noise(self, context_latents, seed):
        _ = seed
        return torch.zeros_like(context_latents)

    def get_x0_from_noise(self, zt, vt, t):
        return zt - vt * t.unsqueeze(-1).unsqueeze(-1)

    def renoise(self, x, t, noise=None):
        _ = t
        _ = noise
        return x


class AceStepTurboProgressTests(unittest.TestCase):
    def test_progress_callback_fires_once_per_step_including_final_step(self):
        host = _FakeTurboHost()
        updates = []
        base = torch.zeros((1, 2, 2), dtype=torch.float32)
        mask = torch.ones((1, 2), dtype=torch.float32)
        cover_mask = torch.zeros((1,), dtype=torch.float32)

        AceStepConditionGenerationModel.generate_audio(
            host,
            text_hidden_states=base,
            text_attention_mask=mask,
            lyric_hidden_states=base,
            lyric_attention_mask=mask,
            refer_audio_acoustic_hidden_states_packed=base,
            refer_audio_order_mask=mask,
            src_latents=base,
            chunk_masks=base,
            is_covers=cover_mask,
            silence_latent=base,
            attention_mask=mask,
            seed=0,
            infer_method="ode",
            timesteps=[1.0, 0.5],
            progress_callback=lambda step, total, desc: updates.append((step, total, desc)),
        )

        self.assertEqual(
            updates,
            [
                (1, 2, "DiT diffusion..."),
                (2, 2, "DiT diffusion..."),
            ],
        )


if __name__ == "__main__":
    unittest.main()
