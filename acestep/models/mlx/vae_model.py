# Pure MLX re-implementation of diffusers' AutoencoderOobleck for Apple Silicon.
#
# Architecture mirrors the PyTorch version exactly:
#   Snake1d -> OobleckResidualUnit -> EncoderBlock / DecoderBlock
#   -> OobleckEncoder / OobleckDecoder -> MLXAutoEncoderOobleck
#
# All operations use MLX channels-last (NLC) convention internally.
# The public encode/decode API accepts and returns NLC arrays.

import math
import logging
from typing import List, Optional, Tuple

import mlx.core as mx
import mlx.nn as nn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snake1d Activation
# ---------------------------------------------------------------------------

class MLXSnake1d(nn.Module):
    """Snake activation: x + (1/beta) * sin(alpha * x)^2.

    Parameters ``alpha`` and ``beta`` are stored as 1-D vectors of shape [C]
    and broadcast over (B, L) automatically.  When ``logscale=True`` (default)
    the actual scale is ``exp(alpha)`` / ``exp(beta)``.
    """

    def __init__(self, hidden_dim: int, logscale: bool = True):
        super().__init__()
        self.alpha = mx.zeros(hidden_dim)
        self.beta = mx.zeros(hidden_dim)
        self.logscale = logscale

    def __call__(self, x: mx.array) -> mx.array:
        # x: [B, L, C]  (NLC)
        # NOTE: Upcast to float32 for exp/sin/power to prevent overflow with float16
        # weights (exp overflows float16 at alpha > ~11).  This is only a problem
        # if the weights are in float16.  The surrounding
        # Conv1d layers still run in the caller's dtype (float16) for speed.

        # This is the original code that works with float16 weights, if we end up needing to
        # use float16 weights. please use this code instead
        # alpha = mx.exp(self.alpha.astype(mx.float32)) if self.logscale else self.alpha
        # beta = mx.exp(self.beta.astype(mx.float32)) if self.logscale else self.beta
        # x_f32 = x.astype(mx.float32)
        # result = x_f32 + mx.reciprocal(beta + 1e-9) * mx.power(mx.sin(alpha * x_f32), 2)
        # return result.astype(x.dtype)
        alpha = mx.exp(self.alpha) if self.logscale else self.alpha
        beta = mx.exp(self.beta) if self.logscale else self.beta
        # All ops broadcast [C] over [B, L, C]
        return x + mx.reciprocal(beta + 1e-9) * mx.power(mx.sin(alpha * x), 2)


# ---------------------------------------------------------------------------
# Residual Unit
# ---------------------------------------------------------------------------

class MLXOobleckResidualUnit(nn.Module):
    """Two weight-normalised Conv1d layers (k=7 dilated + k=1) wrapped with
    Snake1d activations and a residual skip connection."""

    def __init__(self, dimension: int = 16, dilation: int = 1):
        super().__init__()
        pad = ((7 - 1) * dilation) // 2

        self.snake1 = MLXSnake1d(dimension)
        self.conv1 = nn.Conv1d(
            dimension, dimension, kernel_size=7, dilation=dilation, padding=pad
        )
        self.snake2 = MLXSnake1d(dimension)
        self.conv2 = nn.Conv1d(dimension, dimension, kernel_size=1)

    def __call__(self, hidden_state: mx.array) -> mx.array:
        # hidden_state: [B, L, C]
        output = self.conv1(self.snake1(hidden_state))
        output = self.conv2(self.snake2(output))

        # Safety trim (should be no-op with correct padding)
        padding = (hidden_state.shape[1] - output.shape[1]) // 2
        if padding > 0:
            hidden_state = hidden_state[:, padding:-padding, :]

        return hidden_state + output


# ---------------------------------------------------------------------------
# Encoder / Decoder Blocks
# ---------------------------------------------------------------------------

class MLXOobleckEncoderBlock(nn.Module):
    """3 residual units (dilations 1, 3, 9) -> Snake -> strided Conv1d down."""

    def __init__(self, input_dim: int, output_dim: int, stride: int = 1):
        super().__init__()
        self.res_unit1 = MLXOobleckResidualUnit(input_dim, dilation=1)
        self.res_unit2 = MLXOobleckResidualUnit(input_dim, dilation=3)
        self.res_unit3 = MLXOobleckResidualUnit(input_dim, dilation=9)
        self.snake1 = MLXSnake1d(input_dim)
        self.conv1 = nn.Conv1d(
            input_dim,
            output_dim,
            kernel_size=2 * stride,
            stride=stride,
            padding=math.ceil(stride / 2),
        )

    def __call__(self, hidden_state: mx.array) -> mx.array:
        hidden_state = self.res_unit1(hidden_state)
        hidden_state = self.res_unit2(hidden_state)
        hidden_state = self.snake1(self.res_unit3(hidden_state))
        hidden_state = self.conv1(hidden_state)
        return hidden_state


class MLXOobleckDecoderBlock(nn.Module):
    """Snake -> strided ConvTranspose1d up -> 3 residual units (dilations 1, 3, 9)."""

    def __init__(self, input_dim: int, output_dim: int, stride: int = 1):
        super().__init__()
        self.snake1 = MLXSnake1d(input_dim)
        self.conv_t1 = nn.ConvTranspose1d(
            input_dim,
            output_dim,
            kernel_size=2 * stride,
            stride=stride,
            padding=math.ceil(stride / 2),
        )
        self.res_unit1 = MLXOobleckResidualUnit(output_dim, dilation=1)
        self.res_unit2 = MLXOobleckResidualUnit(output_dim, dilation=3)
        self.res_unit3 = MLXOobleckResidualUnit(output_dim, dilation=9)

    def __call__(self, hidden_state: mx.array) -> mx.array:
        hidden_state = self.snake1(hidden_state)
        hidden_state = self.conv_t1(hidden_state)
        hidden_state = self.res_unit1(hidden_state)
        hidden_state = self.res_unit2(hidden_state)
        hidden_state = self.res_unit3(hidden_state)
        return hidden_state


# ---------------------------------------------------------------------------
# Encoder / Decoder
# ---------------------------------------------------------------------------

class MLXOobleckEncoder(nn.Module):
    """Oobleck Encoder: Conv1d -> N encoder blocks -> Snake -> Conv1d."""

    def __init__(
        self,
        encoder_hidden_size: int,
        audio_channels: int,
        downsampling_ratios: List[int],
        channel_multiples: List[int],
    ):
        super().__init__()
        strides = downsampling_ratios
        cm = [1] + list(channel_multiples)

        self.conv1 = nn.Conv1d(
            audio_channels, encoder_hidden_size, kernel_size=7, padding=3
        )

        self.block = []
        for i, stride in enumerate(strides):
            self.block.append(
                MLXOobleckEncoderBlock(
                    input_dim=encoder_hidden_size * cm[i],
                    output_dim=encoder_hidden_size * cm[i + 1],
                    stride=stride,
                )
            )

        d_model = encoder_hidden_size * cm[-1]
        self.snake1 = MLXSnake1d(d_model)
        self.conv2 = nn.Conv1d(d_model, encoder_hidden_size, kernel_size=3, padding=1)

    def __call__(self, hidden_state: mx.array) -> mx.array:
        hidden_state = self.conv1(hidden_state)
        for module in self.block:
            hidden_state = module(hidden_state)
        hidden_state = self.snake1(hidden_state)
        hidden_state = self.conv2(hidden_state)
        return hidden_state


class MLXOobleckDecoder(nn.Module):
    """Oobleck Decoder: Conv1d -> N decoder blocks -> Snake -> Conv1d."""

    def __init__(
        self,
        channels: int,
        input_channels: int,
        audio_channels: int,
        upsampling_ratios: List[int],
        channel_multiples: List[int],
    ):
        super().__init__()
        strides = upsampling_ratios
        cm = [1] + list(channel_multiples)

        self.conv1 = nn.Conv1d(
            input_channels, channels * cm[-1], kernel_size=7, padding=3
        )

        self.block = []
        for i, stride in enumerate(strides):
            self.block.append(
                MLXOobleckDecoderBlock(
                    input_dim=channels * cm[len(strides) - i],
                    output_dim=channels * cm[len(strides) - i - 1],
                    stride=stride,
                )
            )

        self.snake1 = MLXSnake1d(channels)
        self.conv2 = nn.Conv1d(
            channels, audio_channels, kernel_size=7, padding=3, bias=False
        )

    def __call__(self, hidden_state: mx.array) -> mx.array:
        hidden_state = self.conv1(hidden_state)
        for layer in self.block:
            hidden_state = layer(hidden_state)
        hidden_state = self.snake1(hidden_state)
        hidden_state = self.conv2(hidden_state)
        return hidden_state


# ---------------------------------------------------------------------------
# Full VAE
# ---------------------------------------------------------------------------

class MLXAutoEncoderOobleck(nn.Module):
    """Pure-MLX re-implementation of ``diffusers.AutoencoderOobleck``.

    Default configuration matches the Stable Audio / ACE-Step VAE:
        encoder_hidden_size  = 128
        downsampling_ratios  = [2, 4, 4, 8, 8]   (hop_length = 2048)
        channel_multiples    = [1, 2, 4, 8, 16]
        decoder_channels     = 128
        decoder_input_channels = 64               (latent dim)
        audio_channels       = 2                  (stereo)

    Data flows in NLC (batch, length, channels) format throughout.
    """

    def __init__(
        self,
        encoder_hidden_size: int = 128,
        downsampling_ratios: Optional[List[int]] = None,
        channel_multiples: Optional[List[int]] = None,
        decoder_channels: int = 128,
        decoder_input_channels: int = 64,
        audio_channels: int = 2,
    ):
        super().__init__()
        if downsampling_ratios is None:
            downsampling_ratios = [2, 4, 4, 8, 8]
        if channel_multiples is None:
            channel_multiples = [1, 2, 4, 8, 16]

        self.encoder_hidden_size = encoder_hidden_size
        self.decoder_input_channels = decoder_input_channels

        self.encoder = MLXOobleckEncoder(
            encoder_hidden_size=encoder_hidden_size,
            audio_channels=audio_channels,
            downsampling_ratios=downsampling_ratios,
            channel_multiples=channel_multiples,
        )
        self.decoder = MLXOobleckDecoder(
            channels=decoder_channels,
            input_channels=decoder_input_channels,
            audio_channels=audio_channels,
            upsampling_ratios=downsampling_ratios[::-1],
            channel_multiples=channel_multiples,
        )

    # -- public API ---------------------------------------------------------

    def encode_and_sample(self, audio_nlc: mx.array) -> mx.array:
        """Encode audio -> sample latent.

        Args:
            audio_nlc: [B, L_audio, C_audio] in NLC format.

        Returns:
            z: [B, L_latent, C_latent] sampled latent.
        """
        h = self.encoder(audio_nlc)  # [B, L', encoder_hidden_size]

        # Diagonal Gaussian: split into mean + log-scale
        mean, scale = mx.split(h, 2, axis=-1)

        # softplus(scale) + epsilon  (numerically stable)
        std = mx.where(scale > 20.0, scale, mx.log(1.0 + mx.exp(scale))) + 1e-4

        noise = mx.random.normal(mean.shape)
        z = mean + std * noise
        return z

    def encode_mean(self, audio_nlc: mx.array) -> mx.array:
        """Encode audio -> return mean (no sampling noise)."""
        h = self.encoder(audio_nlc)
        mean, _scale = mx.split(h, 2, axis=-1)
        return mean

    def decode(self, latents_nlc: mx.array) -> mx.array:
        """Decode latents -> audio.

        Args:
            latents_nlc: [B, L_latent, C_latent] in NLC format.

        Returns:
            audio: [B, L_audio, C_audio] in NLC format.
        """
        return self.decoder(latents_nlc)

    # -- construction helpers -----------------------------------------------

    @classmethod
    def from_pytorch_config(cls, pt_vae) -> "MLXAutoEncoderOobleck":
        """Construct from a PyTorch ``AutoencoderOobleck`` instance's config."""
        cfg = pt_vae.config
        return cls(
            encoder_hidden_size=cfg.encoder_hidden_size,
            downsampling_ratios=list(cfg.downsampling_ratios),
            channel_multiples=list(cfg.channel_multiples),
            decoder_channels=cfg.decoder_channels,
            decoder_input_channels=cfg.decoder_input_channels,
            audio_channels=cfg.audio_channels,
        )
