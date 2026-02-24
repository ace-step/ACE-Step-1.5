# This module re-implements the diffusion transformer decoder from
# modeling_acestep_v15_turbo.py using pure MLX operations for optimal
# performance on Apple Silicon.

import math
from typing import Optional, Tuple

import mlx.core as mx
import mlx.nn as nn


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _rotate_half(x: mx.array) -> mx.array:
    """Rotate the last dimension by splitting in half and swapping with negation."""
    half = x.shape[-1] // 2
    x1 = x[..., :half]
    x2 = x[..., half:]
    return mx.concatenate([-x2, x1], axis=-1)


def _apply_rotary_pos_emb(
    q: mx.array, k: mx.array, cos: mx.array, sin: mx.array
) -> Tuple[mx.array, mx.array]:
    """Apply rotary position embeddings to query and key tensors.

    Args:
        q, k: [B, n_heads, L, head_dim]
        cos, sin: [1, 1, L, head_dim]
    """
    q_embed = (q * cos) + (_rotate_half(q) * sin)
    k_embed = (k * cos) + (_rotate_half(k) * sin)
    return q_embed, k_embed


def _create_sliding_window_mask(
    seq_len: int, window_size: int, dtype: mx.Dtype = mx.float32
) -> mx.array:
    """Create a bidirectional sliding-window additive attention mask.

    Positions within ``window_size`` of each other get ``0``; all others
    receive a large negative value (``-1e9``).

    Returns:
        [1, 1, seq_len, seq_len]
    """
    indices = mx.arange(seq_len)
    # diff[i, j] = |i - j|
    diff = mx.abs(indices[:, None] - indices[None, :])
    zeros = mx.zeros(diff.shape, dtype=dtype)
    neginf = mx.full(diff.shape, -1e9, dtype=dtype)
    mask = mx.where(diff <= window_size, zeros, neginf)
    return mask[None, None, :, :]  # [1, 1, L, L]


# ---------------------------------------------------------------------------
# Rotary Position Embedding
# ---------------------------------------------------------------------------

class MLXRotaryEmbedding(nn.Module):
    """Pre-computes and caches cos/sin tables for rotary position embeddings."""

    def __init__(self, head_dim: int, max_len: int = 32768, base: float = 1_000_000.0):
        super().__init__()
        self.head_dim = head_dim
        self.max_len = max_len
        self.base = base

        inv_freq = 1.0 / (
            base ** (mx.arange(0, head_dim, 2).astype(mx.float32) / head_dim)
        )
        positions = mx.arange(max_len).astype(mx.float32)
        freqs = positions[:, None] * inv_freq[None, :]  # [max_len, head_dim//2]
        freqs = mx.concatenate([freqs, freqs], axis=-1)  # [max_len, head_dim]
        self._cos = mx.cos(freqs)  # [max_len, head_dim]
        self._sin = mx.sin(freqs)  # [max_len, head_dim]

    def __call__(self, seq_len: int) -> Tuple[mx.array, mx.array]:
        """Return (cos, sin) each shaped [1, 1, seq_len, head_dim]."""
        cos = self._cos[:seq_len][None, None, :, :]
        sin = self._sin[:seq_len][None, None, :, :]
        return cos, sin


# ---------------------------------------------------------------------------
# Cross-Attention KV Cache
# ---------------------------------------------------------------------------

class MLXCrossAttentionCache:
    """Simple KV cache for cross-attention layers.

    Cross-attention K/V are computed from encoder hidden states once on the
    first diffusion step and re-used for all subsequent steps.
    """

    def __init__(self):
        self._keys: dict[int, mx.array] = {}
        self._values: dict[int, mx.array] = {}
        self._updated: set[int] = set()

    def update(self, key: mx.array, value: mx.array, layer_idx: int):
        self._keys[layer_idx] = key
        self._values[layer_idx] = value
        self._updated.add(layer_idx)

    def is_updated(self, layer_idx: int) -> bool:
        return layer_idx in self._updated

    def get(self, layer_idx: int) -> Tuple[mx.array, mx.array]:
        return self._keys[layer_idx], self._values[layer_idx]


# ---------------------------------------------------------------------------
# Core Layers
# ---------------------------------------------------------------------------

class MLXSwiGLUMLP(nn.Module):
    """SwiGLU MLP (equivalent to Qwen3MLP): gate * silu(gate_proj) * up_proj."""

    def __init__(self, hidden_size: int, intermediate_size: int):
        super().__init__()
        self.gate_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.up_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, hidden_size, bias=False)

    def __call__(self, x: mx.array) -> mx.array:
        return self.down_proj(nn.silu(self.gate_proj(x)) * self.up_proj(x))


class MLXAttention(nn.Module):
    """Multi-head attention with QK-RMSNorm for the AceStep DiT.

    Supports both self-attention (with RoPE) and cross-attention (with
    optional KV caching).
    """

    def __init__(
        self,
        hidden_size: int,
        num_attention_heads: int,
        num_key_value_heads: int,
        head_dim: int,
        rms_norm_eps: float,
        attention_bias: bool,
        layer_idx: int,
        is_cross_attention: bool = False,
        sliding_window: Optional[int] = None,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads = num_attention_heads
        self.num_kv_heads = num_key_value_heads
        self.head_dim = head_dim
        self.n_rep = num_attention_heads // num_key_value_heads
        self.scale = head_dim ** -0.5
        self.layer_idx = layer_idx
        self.is_cross_attention = is_cross_attention
        self.sliding_window = sliding_window

        self.q_proj = nn.Linear(hidden_size, num_attention_heads * head_dim, bias=attention_bias)
        self.k_proj = nn.Linear(hidden_size, num_key_value_heads * head_dim, bias=attention_bias)
        self.v_proj = nn.Linear(hidden_size, num_key_value_heads * head_dim, bias=attention_bias)
        self.o_proj = nn.Linear(num_attention_heads * head_dim, hidden_size, bias=attention_bias)

        self.q_norm = nn.RMSNorm(head_dim, eps=rms_norm_eps)
        self.k_norm = nn.RMSNorm(head_dim, eps=rms_norm_eps)

    @staticmethod
    def _repeat_kv(x: mx.array, n_rep: int) -> mx.array:
        """Repeat KV heads for GQA: [B, n_kv, L, D] -> [B, n_kv*n_rep, L, D]."""
        if n_rep == 1:
            return x
        B, n_kv, L, D = x.shape
        x = mx.expand_dims(x, axis=2)                  # [B, n_kv, 1, L, D]
        x = mx.broadcast_to(x, (B, n_kv, n_rep, L, D))
        return x.reshape(B, n_kv * n_rep, L, D)

    def __call__(
        self,
        hidden_states: mx.array,
        position_cos_sin: Optional[Tuple[mx.array, mx.array]] = None,
        attention_mask: Optional[mx.array] = None,
        encoder_hidden_states: Optional[mx.array] = None,
        cache: Optional[MLXCrossAttentionCache] = None,
        use_cache: bool = False,
    ) -> mx.array:
        B, L, _ = hidden_states.shape

        # Project queries (always from hidden_states)
        q = self.q_proj(hidden_states)
        q = self.q_norm(q.reshape(B, L, self.num_heads, self.head_dim))
        q = q.transpose(0, 2, 1, 3)  # [B, n_heads, L, D]

        if self.is_cross_attention and encoder_hidden_states is not None:
            # Cross-attention: K,V come from encoder
            if cache is not None and cache.is_updated(self.layer_idx):
                k, v = cache.get(self.layer_idx)
            else:
                enc_L = encoder_hidden_states.shape[1]
                k = self.k_proj(encoder_hidden_states)
                k = self.k_norm(k.reshape(B, enc_L, self.num_kv_heads, self.head_dim))
                k = k.transpose(0, 2, 1, 3)
                v = self.v_proj(encoder_hidden_states).reshape(
                    B, enc_L, self.num_kv_heads, self.head_dim
                ).transpose(0, 2, 1, 3)
                if cache is not None and use_cache:
                    cache.update(k, v, self.layer_idx)
        else:
            # Self-attention: K,V come from hidden_states
            k = self.k_proj(hidden_states)
            k = self.k_norm(k.reshape(B, L, self.num_kv_heads, self.head_dim))
            k = k.transpose(0, 2, 1, 3)
            v = self.v_proj(hidden_states).reshape(
                B, L, self.num_kv_heads, self.head_dim
            ).transpose(0, 2, 1, 3)

            # Apply RoPE to self-attention Q,K
            if position_cos_sin is not None:
                cos, sin = position_cos_sin
                q, k = _apply_rotary_pos_emb(q, k, cos, sin)

        # GQA: repeat KV heads to match Q heads
        k = self._repeat_kv(k, self.n_rep)
        v = self._repeat_kv(v, self.n_rep)

        # Scaled dot-product attention
        attn_out = mx.fast.scaled_dot_product_attention(
            q, k, v, scale=self.scale, mask=attention_mask
        )

        # Merge heads and project output: [B, n_heads, L, D] -> [B, L, hidden]
        attn_out = attn_out.transpose(0, 2, 1, 3).reshape(B, L, -1)
        return self.o_proj(attn_out)


# ---------------------------------------------------------------------------
# DiT Layer
# ---------------------------------------------------------------------------

class MLXDiTLayer(nn.Module):
    """A single DiT transformer layer with AdaLN modulation.

    Implements:
        1. Self-attention with adaptive layer norm (AdaLN)
        2. Cross-attention to encoder hidden states
        3. Feed-forward MLP with adaptive layer norm
    """

    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        num_attention_heads: int,
        num_key_value_heads: int,
        head_dim: int,
        rms_norm_eps: float,
        attention_bias: bool,
        layer_idx: int,
        layer_type: str,
        sliding_window: Optional[int] = None,
    ):
        super().__init__()
        self.layer_type = layer_type
        sw = sliding_window if layer_type == "sliding_attention" else None

        # 1. Self-attention
        self.self_attn_norm = nn.RMSNorm(hidden_size, eps=rms_norm_eps)
        self.self_attn = MLXAttention(
            hidden_size=hidden_size,
            num_attention_heads=num_attention_heads,
            num_key_value_heads=num_key_value_heads,
            head_dim=head_dim,
            rms_norm_eps=rms_norm_eps,
            attention_bias=attention_bias,
            layer_idx=layer_idx,
            is_cross_attention=False,
            sliding_window=sw,
        )

        # 2. Cross-attention
        self.cross_attn_norm = nn.RMSNorm(hidden_size, eps=rms_norm_eps)
        self.cross_attn = MLXAttention(
            hidden_size=hidden_size,
            num_attention_heads=num_attention_heads,
            num_key_value_heads=num_key_value_heads,
            head_dim=head_dim,
            rms_norm_eps=rms_norm_eps,
            attention_bias=attention_bias,
            layer_idx=layer_idx,
            is_cross_attention=True,
        )

        # 3. MLP
        self.mlp_norm = nn.RMSNorm(hidden_size, eps=rms_norm_eps)
        self.mlp = MLXSwiGLUMLP(hidden_size, intermediate_size)

        # AdaLN modulation table (6 values: shift/scale/gate for self-attn & MLP)
        self.scale_shift_table = mx.zeros((1, 6, hidden_size))

    def __call__(
        self,
        hidden_states: mx.array,
        position_cos_sin: Tuple[mx.array, mx.array],
        temb: mx.array,
        self_attn_mask: Optional[mx.array],
        encoder_hidden_states: Optional[mx.array],
        encoder_attention_mask: Optional[mx.array],
        cache: Optional[MLXCrossAttentionCache] = None,
        use_cache: bool = False,
    ) -> mx.array:
        # AdaLN modulation from timestep embeddings
        # scale_shift_table: [1, 6, D], temb: [B, 6, D]
        modulation = self.scale_shift_table + temb  # [B, 6, D]
        parts = mx.split(modulation, 6, axis=1)
        # Each part: [B, 1, D]
        shift_msa, scale_msa, gate_msa = parts[0], parts[1], parts[2]
        c_shift_msa, c_scale_msa, c_gate_msa = parts[3], parts[4], parts[5]

        # Step 1: Self-attention with AdaLN
        normed = self.self_attn_norm(hidden_states)
        normed = normed * (1.0 + scale_msa) + shift_msa
        attn_out = self.self_attn(
            normed,
            position_cos_sin=position_cos_sin,
            attention_mask=self_attn_mask,
        )
        hidden_states = hidden_states + attn_out * gate_msa

        # Step 2: Cross-attention
        normed = self.cross_attn_norm(hidden_states)
        cross_out = self.cross_attn(
            normed,
            encoder_hidden_states=encoder_hidden_states,
            attention_mask=encoder_attention_mask,
            cache=cache,
            use_cache=use_cache,
        )
        hidden_states = hidden_states + cross_out

        # Step 3: MLP with AdaLN
        normed = self.mlp_norm(hidden_states)
        normed = normed * (1.0 + c_scale_msa) + c_shift_msa
        ff_out = self.mlp(normed)
        hidden_states = hidden_states + ff_out * c_gate_msa

        return hidden_states


# ---------------------------------------------------------------------------
# Timestep Embedding
# ---------------------------------------------------------------------------

class MLXTimestepEmbedding(nn.Module):
    """Sinusoidal timestep embedding followed by MLP."""

    def __init__(self, in_channels: int = 256, time_embed_dim: int = 2048, scale: float = 1000.0):
        super().__init__()
        self.in_channels = in_channels
        self.scale = scale

        self.linear_1 = nn.Linear(in_channels, time_embed_dim, bias=True)
        self.act1 = nn.SiLU()
        self.linear_2 = nn.Linear(time_embed_dim, time_embed_dim, bias=True)
        self.act2 = nn.SiLU()
        self.time_proj = nn.Linear(time_embed_dim, time_embed_dim * 6, bias=True)

    def _sinusoidal_embedding(self, t: mx.array, dim: int, max_period: int = 10000) -> mx.array:
        """Create sinusoidal timestep embeddings.

        Args:
            t: 1-D array of shape [N]
            dim: embedding dimension
        Returns:
            [N, dim]
        """
        t = t * self.scale
        half = dim // 2
        freqs = mx.exp(
            -math.log(max_period)
            * mx.arange(half).astype(mx.float32) / half
        )
        args = t[:, None].astype(mx.float32) * freqs[None, :]
        embedding = mx.concatenate([mx.cos(args), mx.sin(args)], axis=-1)
        if dim % 2:
            embedding = mx.concatenate(
                [embedding, mx.zeros_like(embedding[:, :1])], axis=-1
            )
        return embedding

    def __call__(self, t: mx.array) -> Tuple[mx.array, mx.array]:
        """
        Args:
            t: [B] timestep values
        Returns:
            temb: [B, D]
            timestep_proj: [B, 6, D]
        """
        t_freq = self._sinusoidal_embedding(t, self.in_channels)
        temb = self.linear_1(t_freq.astype(t.dtype))
        temb = self.act1(temb)
        temb = self.linear_2(temb)
        proj = self.time_proj(self.act2(temb))  # [B, D*6]
        timestep_proj = proj.reshape(proj.shape[0], 6, -1)  # [B, 6, D]
        return temb, timestep_proj


# ---------------------------------------------------------------------------
# Full DiT Decoder
# ---------------------------------------------------------------------------

class MLXDiTDecoder(nn.Module):
    """Native MLX implementation of AceStepDiTModel (the diffusion transformer decoder).

    Mirrors the PyTorch ``AceStepDiTModel`` class exactly:
        - Patch-based input projection (Conv1d)
        - Timestep conditioning via dual TimestepEmbedding
        - N DiT transformer layers with self/cross-attention and AdaLN
        - Patch-based output projection (ConvTranspose1d)
        - Adaptive output layer norm
    """

    def __init__(
        self,
        hidden_size: int = 2048,
        intermediate_size: int = 6144,
        num_hidden_layers: int = 24,
        num_attention_heads: int = 16,
        num_key_value_heads: int = 8,
        head_dim: int = 128,
        rms_norm_eps: float = 1e-6,
        attention_bias: bool = False,
        in_channels: int = 192,
        audio_acoustic_hidden_dim: int = 64,
        patch_size: int = 2,
        sliding_window: int = 128,
        layer_types: Optional[list] = None,
        rope_theta: float = 1_000_000.0,
        max_position_embeddings: int = 32768,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.patch_size = patch_size
        inner_dim = hidden_size

        if layer_types is None:
            layer_types = [
                "sliding_attention" if bool((i + 1) % 2) else "full_attention"
                for i in range(num_hidden_layers)
            ]

        # Rotary position embeddings
        self.rotary_emb = MLXRotaryEmbedding(
            head_dim, max_len=max_position_embeddings, base=rope_theta
        )

        # Input projection: Conv1d patch embedding
        # MLX Conv1d uses channels-last: [B, L, C] -> [B, L//stride, out_C]
        self.proj_in = nn.Conv1d(
            in_channels=in_channels,
            out_channels=inner_dim,
            kernel_size=patch_size,
            stride=patch_size,
            padding=0,
        )

        # Timestep embeddings (two: t and t-r)
        self.time_embed = MLXTimestepEmbedding(in_channels=256, time_embed_dim=inner_dim)
        self.time_embed_r = MLXTimestepEmbedding(in_channels=256, time_embed_dim=inner_dim)

        # Condition embedder
        self.condition_embedder = nn.Linear(inner_dim, inner_dim, bias=True)

        # Transformer layers
        self.layers = [
            MLXDiTLayer(
                hidden_size=hidden_size,
                intermediate_size=intermediate_size,
                num_attention_heads=num_attention_heads,
                num_key_value_heads=num_key_value_heads,
                head_dim=head_dim,
                rms_norm_eps=rms_norm_eps,
                attention_bias=attention_bias,
                layer_idx=i,
                layer_type=layer_types[i],
                sliding_window=sliding_window,
            )
            for i in range(num_hidden_layers)
        ]

        # Output
        self.norm_out = nn.RMSNorm(inner_dim, eps=rms_norm_eps)
        self.proj_out = nn.ConvTranspose1d(
            in_channels=inner_dim,
            out_channels=audio_acoustic_hidden_dim,
            kernel_size=patch_size,
            stride=patch_size,
            padding=0,
        )

        # Output adaptive layer norm modulation (2 values: shift, scale)
        self.scale_shift_table = mx.zeros((1, 2, inner_dim))

        # Pre-compute sliding window mask (will be set on first forward)
        self._sliding_masks: dict[int, mx.array] = {}
        self._sliding_window = sliding_window
        self._layer_types = layer_types

    def _get_sliding_mask(self, seq_len: int, dtype: mx.Dtype) -> mx.array:
        if seq_len not in self._sliding_masks:
            self._sliding_masks[seq_len] = _create_sliding_window_mask(
                seq_len, self._sliding_window, dtype
            )
        return self._sliding_masks[seq_len]

    def __call__(
        self,
        hidden_states: mx.array,
        timestep: mx.array,
        timestep_r: mx.array,
        encoder_hidden_states: mx.array,
        context_latents: mx.array,
        cache: Optional[MLXCrossAttentionCache] = None,
        use_cache: bool = True,
    ) -> Tuple[mx.array, Optional[MLXCrossAttentionCache]]:
        """
        Args:
            hidden_states: noisy latents [B, T, 64]
            timestep: [B] current timestep
            timestep_r: [B] reference timestep
            encoder_hidden_states: [B, enc_L, D] from condition encoder
            context_latents: [B, T, C_ctx] (src_latents + chunk_masks)
            cache: cross-attention KV cache
            use_cache: whether to cache cross-attention KV

        Returns:
            (output_hidden_states, cache)
        """
        # Timestep embeddings
        temb_t, proj_t = self.time_embed(timestep)
        temb_r, proj_r = self.time_embed_r(timestep - timestep_r)
        temb = temb_t + temb_r          # [B, D]
        timestep_proj = proj_t + proj_r  # [B, 6, D]

        # Concatenate context with hidden states: [B, T, C_ctx + 64] -> [B, T, in_channels]
        hidden_states = mx.concatenate([context_latents, hidden_states], axis=-1)

        original_seq_len = hidden_states.shape[1]

        # Pad to multiple of patch_size
        pad_length = 0
        if hidden_states.shape[1] % self.patch_size != 0:
            pad_length = self.patch_size - (hidden_states.shape[1] % self.patch_size)
            # Pad along time dimension
            padding = mx.zeros(
                (hidden_states.shape[0], pad_length, hidden_states.shape[2]),
                dtype=hidden_states.dtype,
            )
            hidden_states = mx.concatenate([hidden_states, padding], axis=1)

        # Patch embedding: [B, T, in_ch] -> [B, T//patch, D]
        hidden_states = self.proj_in(hidden_states)

        # Project encoder states
        encoder_hidden_states = self.condition_embedder(encoder_hidden_states)

        seq_len = hidden_states.shape[1]
        dtype = hidden_states.dtype

        # Position embeddings (RoPE)
        cos, sin = self.rotary_emb(seq_len)

        # Attention masks
        # Self-attention: full layers get None; sliding layers get windowed mask
        # Cross-attention: always None (no masking)
        sliding_mask = None
        has_sliding = any(lt == "sliding_attention" for lt in self._layer_types)
        if has_sliding:
            sliding_mask = self._get_sliding_mask(seq_len, dtype)

        # Process through transformer layers
        for layer in self.layers:
            self_attn_mask = sliding_mask if layer.layer_type == "sliding_attention" else None
            hidden_states = layer(
                hidden_states,
                position_cos_sin=(cos, sin),
                temb=timestep_proj,
                self_attn_mask=self_attn_mask,
                encoder_hidden_states=encoder_hidden_states,
                encoder_attention_mask=None,
                cache=cache,
                use_cache=use_cache,
            )

        # Output adaptive layer norm
        shift, scale = mx.split(
            self.scale_shift_table + mx.expand_dims(temb, axis=1), 2, axis=1
        )
        hidden_states = self.norm_out(hidden_states) * (1.0 + scale) + shift

        # De-patchify: [B, T//patch, D] -> [B, T, out_channels]
        hidden_states = self.proj_out(hidden_states)

        # Crop back to original sequence length
        hidden_states = hidden_states[:, :original_seq_len, :]

        return hidden_states, cache

    @classmethod
    def from_config(cls, config) -> "MLXDiTDecoder":
        """Construct from an AceStepConfig (transformers PretrainedConfig)."""
        return cls(
            hidden_size=config.hidden_size,
            intermediate_size=config.intermediate_size,
            num_hidden_layers=config.num_hidden_layers,
            num_attention_heads=config.num_attention_heads,
            num_key_value_heads=config.num_key_value_heads,
            head_dim=getattr(config, "head_dim", config.hidden_size // config.num_attention_heads),
            rms_norm_eps=config.rms_norm_eps,
            attention_bias=config.attention_bias,
            in_channels=config.in_channels,
            audio_acoustic_hidden_dim=config.audio_acoustic_hidden_dim,
            patch_size=config.patch_size,
            sliding_window=config.sliding_window if config.sliding_window else 128,
            layer_types=config.layer_types,
            rope_theta=config.rope_theta,
            max_position_embeddings=config.max_position_embeddings,
        )
