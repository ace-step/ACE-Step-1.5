"""Wavelet-domain DCW primitives — the actual ``dcw_low``/``high``/``double``/``pix`` math.

Verbatim from the paper's reference implementation
(``AMAP-ML/DCW/FlowMatchEulerDiscreteScheduler.py``) but adapted to the
1-D temporal layout of ACE-Step latents (``[B, T, C]``):

* The reference operates on 2-D image latents with ``DWT2DForward``;
  ours uses ``DWT1DForward`` along the temporal axis after transposing
  ``[B, T, C] → [B, C, T]``.
* ``pytorch_wavelets`` zero-pads odd ``T`` to the next even before the
  filter bank, so the IDWT output is one sample longer than the input.
  We trim ``x_new[:, :, :out_T]`` so ACE-Step's odd-duration latents
  round-trip cleanly.
"""

from __future__ import annotations

import torch

from .dcw_loader import WAVELET_CACHE


def _btc_to_bct(x: torch.Tensor) -> torch.Tensor:
    """Rearrange ACE-Step latents from ``[B, T, C]`` to ``[B, C, T]``."""
    return x.transpose(1, 2).contiguous()


def _bct_to_btc(x: torch.Tensor) -> torch.Tensor:
    """Inverse of :func:`_btc_to_bct`."""
    return x.transpose(1, 2).contiguous()


def dcw_pix(x: torch.Tensor, y: torch.Tensor, scaler: float) -> torch.Tensor:
    """Pixel/latent-space differential correction (no wavelet transform).

    Matches the ``dcw_pix`` baseline in the DCW reference code — corrects
    directly in latent space.  Useful as an ablation and as the fallback
    on platforms without ``pytorch_wavelets``.
    """
    if scaler == 0.0:
        return x
    return x + scaler * (x - y)


def _dwt_pair(x: torch.Tensor, y: torch.Tensor, wavelet: str):
    """Run DWT on both latents.

    Returns ``(xl, xh, yl, yh, iwt, out_T)`` or ``None`` if the optional
    ``pytorch_wavelets`` dependency is missing.

    ``out_T`` is the original time length of ``x`` — we slice the IDWT
    output back to this length because ``pytorch_wavelets`` pads odd-T
    inputs up to the next even value before running the filter bank.
    """
    modules = WAVELET_CACHE.get(x.device, x.dtype, wavelet)
    if modules is None:
        return None
    dwt, iwt = modules
    x_bct = _btc_to_bct(x.to(torch.float32))
    y_bct = _btc_to_bct(y.to(torch.float32))
    xl, xh = dwt(x_bct)
    yl, yh = dwt(y_bct)
    return xl, xh, yl, yh, iwt, x.shape[1]


def dcw_low(
    x: torch.Tensor, y: torch.Tensor, scaler: float, wavelet: str = "haar"
) -> torch.Tensor:
    """Apply differential correction to the low-frequency sub-band only.

    Implements Eq. 18 / 20 of the DCW paper:

    * ``xL, xH = DWT(x)``;  ``yL, yH = DWT(y)``
    * ``xL ← xL + scaler · (xL − yL)``
    * ``x_new = IDWT(xL, xH)``

    Args:
        x: Current latent ``x_next`` after the sampler step, shape ``[B, T, C]``.
        y: Predicted clean sample ``denoised = x − v · t``, shape ``[B, T, C]``.
        scaler: Correction strength.  ``0`` short-circuits to identity.
        wavelet: PyWavelets basis, e.g. ``"haar"`` / ``"db4"`` / ``"sym8"``.

    Returns:
        Corrected latent with the same shape and dtype as ``x``.
    """
    if scaler == 0.0:
        return x
    pair = _dwt_pair(x, y, wavelet)
    if pair is None:
        return x
    xl, xh, yl, _yh, iwt, out_T = pair
    xl = xl + scaler * (xl - yl)
    x_new = iwt((xl, xh))
    return _bct_to_btc(x_new[:, :, :out_T]).to(dtype=x.dtype)


def dcw_high(
    x: torch.Tensor, y: torch.Tensor, scaler: float, wavelet: str = "haar"
) -> torch.Tensor:
    """Apply differential correction to the high-frequency sub-band only."""
    if scaler == 0.0:
        return x
    pair = _dwt_pair(x, y, wavelet)
    if pair is None:
        return x
    xl, xh, _yl, yh, iwt, out_T = pair
    xh_new = [xhi + scaler * (xhi - yhi) for xhi, yhi in zip(xh, yh, strict=True)]
    x_new = iwt((xl, xh_new))
    return _bct_to_btc(x_new[:, :, :out_T]).to(dtype=x.dtype)


def dcw_double(
    x: torch.Tensor,
    y: torch.Tensor,
    low_scaler: float,
    high_scaler: float,
    wavelet: str = "haar",
) -> torch.Tensor:
    """Apply differential correction to both low- and high-frequency bands."""
    if low_scaler == 0.0 and high_scaler == 0.0:
        return x
    pair = _dwt_pair(x, y, wavelet)
    if pair is None:
        return x
    xl, xh, yl, yh, iwt, out_T = pair
    if low_scaler != 0.0:
        xl = xl + low_scaler * (xl - yl)
    if high_scaler != 0.0:
        xh = [xhi + high_scaler * (xhi - yhi) for xhi, yhi in zip(xh, yh, strict=True)]
    x_new = iwt((xl, xh))
    return _bct_to_btc(x_new[:, :, :out_T]).to(dtype=x.dtype)
