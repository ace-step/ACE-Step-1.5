"""Tests for MLX DiT static buffer materialization."""

import concurrent.futures
import importlib.util
import unittest


@unittest.skipUnless(
    importlib.util.find_spec("mlx.core") is not None,
    "MLX is only available on supported Apple Silicon environments.",
)
class MLXStaticBufferMaterializationTests(unittest.TestCase):
    """Regression coverage for MLX static buffers used from worker threads."""

    def test_rotary_buffers_materialized_before_worker_thread_eval(self):
        """Materialized RoPE tables can be sliced and evaluated in a worker."""
        import mlx.core as mx

        from acestep.models.mlx.dit_model import MLXRotaryEmbedding

        rotary_emb = MLXRotaryEmbedding(head_dim=16, max_len=128)
        rotary_emb.materialize_static_buffers()

        def _worker_eval():
            cos, sin = rotary_emb(32)
            mx.eval(cos, sin)
            return cos.shape, sin.shape

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            cos_shape, sin_shape = executor.submit(_worker_eval).result(timeout=10)

        self.assertEqual(cos_shape, (1, 1, 32, 16))
        self.assertEqual(sin_shape, (1, 1, 32, 16))

    def test_decoder_static_buffer_materialization_is_idempotent(self):
        """Decoder-level materialization delegates safely across repeated calls."""
        from acestep.models.mlx.dit_model import MLXDiTDecoder

        decoder = MLXDiTDecoder(
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=2,
            num_attention_heads=2,
            num_key_value_heads=1,
            head_dim=16,
            in_channels=96,
            audio_acoustic_hidden_dim=64,
            sliding_window=8,
            max_position_embeddings=128,
        )

        decoder.materialize_static_buffers()
        decoder.materialize_static_buffers()
        self.assertIsNotNone(decoder.rotary_emb)

    def test_decoder_forward_runs_from_worker_after_materialization(self):
        """Materialized decoder static buffers support worker-thread forward passes."""
        import mlx.core as mx

        from acestep.models.mlx.dit_model import MLXDiTDecoder

        decoder = MLXDiTDecoder(
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=2,
            num_attention_heads=2,
            num_key_value_heads=1,
            head_dim=16,
            in_channels=96,
            audio_acoustic_hidden_dim=64,
            sliding_window=8,
            max_position_embeddings=128,
            layer_types=["sliding_attention", "full_attention"],
        )
        mx.eval(decoder.parameters())
        decoder.materialize_static_buffers()

        hidden_states = mx.random.normal((1, 8, 64))
        context_latents = mx.random.normal((1, 8, 32))
        encoder_hidden_states = mx.random.normal((1, 4, 32))
        timestep = mx.full((1,), 1.0)
        mx.eval(hidden_states, context_latents, encoder_hidden_states, timestep)

        def _worker_forward():
            out, _ = decoder(
                hidden_states=hidden_states,
                timestep=timestep,
                timestep_r=timestep,
                encoder_hidden_states=encoder_hidden_states,
                context_latents=context_latents,
                cache=None,
                use_cache=False,
            )
            mx.eval(out)
            return out.shape

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            self.assertEqual(executor.submit(_worker_forward).result(timeout=20), (1, 8, 64))

    def test_sliding_mask_cache_is_materialized_for_worker_reuse(self):
        """Cached sliding masks can be evaluated safely from worker threads."""
        import mlx.core as mx

        from acestep.models.mlx.dit_model import MLXDiTDecoder

        decoder = MLXDiTDecoder(
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
            num_key_value_heads=1,
            head_dim=16,
            in_channels=96,
            audio_acoustic_hidden_dim=64,
            sliding_window=8,
            max_position_embeddings=128,
            layer_types=["sliding_attention"],
        )
        mask = decoder._get_sliding_mask(8, mx.float32)

        def _worker_eval():
            mx.eval(mask)
            return mask.shape

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            self.assertEqual(executor.submit(_worker_eval).result(timeout=10), (1, 1, 8, 8))

    def test_sliding_mask_cache_keys_by_dtype(self):
        """Sliding mask cache keeps separate entries for different MLX dtypes."""
        import mlx.core as mx

        from acestep.models.mlx.dit_model import MLXDiTDecoder

        decoder = MLXDiTDecoder(
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
            num_key_value_heads=1,
            head_dim=16,
            in_channels=96,
            audio_acoustic_hidden_dim=64,
            sliding_window=8,
            max_position_embeddings=128,
            layer_types=["sliding_attention"],
        )
        mask_f32 = decoder._get_sliding_mask(8, mx.float32)
        mask_f16 = decoder._get_sliding_mask(8, mx.float16)
        mx.eval(mask_f32, mask_f16)

        self.assertEqual(mask_f32.dtype, mx.float32)
        self.assertEqual(mask_f16.dtype, mx.float16)
