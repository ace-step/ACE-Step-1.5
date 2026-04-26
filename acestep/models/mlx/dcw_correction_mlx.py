"""MLX helpers for Differential Correction in Wavelet domain (DCW).

ACE-Step's MLX diffusion loop (``acestep.models.mlx.dit_generate``) runs on
``mx.array``.  For DCW we want feature parity with the PyTorch path — every
wavelet basis the UI exposes (``haar`` / ``db2`` / ``db4`` / ``sym4`` /
``sym8`` / ``coif2``) should actually affect the output.

Two execution strategies:

* ``haar``: handled natively in MLX with a 2-tap orthogonal filter bank.
  Zero extra dependencies, zero conversions — pure ``mx.array`` ops.
* Any other basis (``db4``, ``sym8`` …): delegate to the PyTorch path via a
  per-step ``mx.array ↔ torch.Tensor`` bridge so ``pytorch_wavelets``'s
  filter-bank implementation is reused verbatim.  Cost is one CPU-side
  numpy round-trip per sampler step; negligible next to a 2-4 B DiT fwd.

The native Haar implementation matches ``pytorch_wavelets.DWT1DForward``
to float-32 noise floor (verified in ``dcw_correction_mlx_test.py``), so
no user will see behaviour divergence between CPU/CUDA and MLX runs at
the same ``dcw_scaler`` / ``dcw_mode`` / ``dcw_wavelet`` triple.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


def _haar_dwt_1d(x):
    """Single-level Haar DWT along the T axis of a ``[B, T, C]`` ``mx.array``.

    Returns ``(low, high)``, each of shape ``[B, T//2, C]``.  If ``T`` is
    odd we zero-pad one sample on the right to mirror
    ``pytorch_wavelets``' ``mode='zero'`` behaviour at the boundary.
    """
    import mlx.core as mx

    T = x.shape[1]
    if T % 2 == 1:
        pad = mx.zeros((x.shape[0], 1, x.shape[2]), dtype=x.dtype)
        x = mx.concatenate([x, pad], axis=1)
    even = x[:, 0::2, :]
    odd = x[:, 1::2, :]
    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    low = (even + odd) * inv_sqrt2
    high = (even - odd) * inv_sqrt2
    return low, high


def _haar_idwt_1d(low, high, out_T: int):
    """Inverse of :func:`_haar_dwt_1d`; returns an array of length ``out_T``."""
    import mlx.core as mx

    inv_sqrt2 = 1.0 / math.sqrt(2.0)
    even = (low + high) * inv_sqrt2
    odd = (low - high) * inv_sqrt2
    # Interleave even/odd back along axis 1 -> shape [B, 2*(T//2), C].
    stacked = mx.stack([even, odd], axis=2)   # [B, T//2, 2, C]
    reconstructed = stacked.reshape(even.shape[0], -1, even.shape[2])
    return reconstructed[:, :out_T, :]


# Cache the warning-once flag so we don't spam the log per-step when
# pytorch_wavelets isn't installed.
_warned_no_pw = False


def _torch_bridge_dcw(
    x_next,
    denoised,
    mode: str,
    s: float,
    hs: float,
    wavelet: str,
):
    """Compute the DCW correction on MLX arrays via pytorch_wavelets.

    One numpy copy per latent; runs on CPU with float32.  Returned as
    ``mx.array`` with the same shape and dtype as the caller's ``x_next``.

    If ``pytorch_wavelets`` is missing we fall back to the native Haar
    implementation and log a one-time warning — the user at least keeps a
    working DCW, just with a different basis than they asked for.
    """
    global _warned_no_pw
    try:
        import torch
        import numpy as np
        from acestep.models.common.dcw_primitives import dcw_low as _dl
        from acestep.models.common.dcw_primitives import dcw_high as _dh
        from acestep.models.common.dcw_primitives import dcw_double as _dd
    except ImportError as exc:  # pragma: no cover — defensive
        if not _warned_no_pw:
            logger.warning(
                "[MLX-DiT] DCW wavelet=%r needs torch + pytorch_wavelets for "
                "the bridge; missing dependency (%s). Falling back to native "
                "Haar for this run.", wavelet, exc,
            )
            _warned_no_pw = True
        T_out = x_next.shape[1]
        xL, xH = _haar_dwt_1d(x_next)
        yL, yH = _haar_dwt_1d(denoised)
        if mode == "low":
            xL = xL + s * (xL - yL)
        elif mode == "high":
            xH = xH + s * (xH - yH)
        elif mode == "double":
            if s != 0.0:
                xL = xL + s * (xL - yL)
            if hs != 0.0:
                xH = xH + hs * (xH - yH)
        return _haar_idwt_1d(xL, xH, T_out)

    import mlx.core as mx

    # Convert mx -> numpy -> torch (float32 on CPU).  MLX's default array
    # device is unified memory on Apple Silicon, so np.array(mx_arr) is a
    # cheap view/copy; on torch side we don't need GPU since DWT is a tiny
    # per-step op next to the DiT forward.
    xn = torch.from_numpy(np.array(x_next, dtype="float32"))
    yn = torch.from_numpy(np.array(denoised, dtype="float32"))

    if mode == "low":
        out = _dl(xn, yn, s, wavelet)
    elif mode == "high":
        out = _dh(xn, yn, s, wavelet)
    elif mode == "double":
        out = _dd(xn, yn, s, hs, wavelet)
    else:
        # "pix" is handled by the caller before we ever get here; and
        # unknown modes were rejected upstream.
        raise ValueError(f"Unexpected dcw_mode={mode!r} in torch bridge")

    # torch -> numpy -> mx; cast back to the caller's dtype.
    return mx.array(out.detach().cpu().numpy()).astype(x_next.dtype)


def apply_mlx_dcw(
    x_next,
    denoised,
    t_curr: float,
    enabled: bool,
    mode: str,
    scaler: float,
    high_scaler: float,
    wavelet: str,
):
    """Apply DCW correction to an MLX latent.

    Dispatches to:
      * a no-op when disabled / zero-scaler / ``t_curr=0``,
      * pure MLX for ``mode="pix"`` (no wavelet transform needed),
      * the native Haar implementation when ``wavelet="haar"``,
      * the PyTorch bridge for any other wavelet basis so the UI's full
        dropdown (``db4`` / ``sym8`` / …) produces the same results as
        the CUDA/CPU PyTorch path.
    """
    if not enabled:
        return x_next

    # Per-mode schedule — see `DCWCorrector.apply` docstring for the
    # paper Eq. 20 / 21 justification.  low decays with t, high is the
    # complementary schedule (weak at high noise, strong near t→0),
    # pix uses the raw scaler (matches FLUX reference).
    t = float(t_curr)
    raw_low = float(scaler)
    raw_high = float(high_scaler)
    low_s = t * raw_low
    high_s = (1.0 - t) * raw_low
    double_high_s = (1.0 - t) * raw_high

    if mode == "pix":
        if raw_low == 0.0:
            return x_next
        return x_next + raw_low * (x_next - denoised)

    if mode == "low":
        s_active = low_s
    elif mode == "high":
        s_active = high_s
    elif mode == "double":
        if low_s == 0.0 and double_high_s == 0.0:
            return x_next
        s_active = None  # handled below
    else:
        raise ValueError(
            f"Invalid dcw_mode='{mode}' on MLX path. "
            "Expected one of 'low', 'high', 'double', 'pix'."
        )

    if mode != "double" and s_active == 0.0:
        return x_next

    if wavelet == "haar":
        T_out = x_next.shape[1]
        xL, xH = _haar_dwt_1d(x_next)
        yL, yH = _haar_dwt_1d(denoised)

        if mode == "low":
            xL = xL + low_s * (xL - yL)
        elif mode == "high":
            xH = xH + high_s * (xH - yH)
        else:  # double
            if low_s != 0.0:
                xL = xL + low_s * (xL - yL)
            if double_high_s != 0.0:
                xH = xH + double_high_s * (xH - yH)
        return _haar_idwt_1d(xL, xH, T_out)

    # Non-Haar wavelets go through the torch bridge so MLX users get the
    # same set of choices (db4, sym8, coif2, …) as PyTorch users.  Pass
    # the already-scheduled coefficients — the bridge just applies them.
    if mode == "low":
        return _torch_bridge_dcw(x_next, denoised, mode, low_s, 0.0, wavelet)
    if mode == "high":
        return _torch_bridge_dcw(x_next, denoised, mode, high_s, 0.0, wavelet)
    return _torch_bridge_dcw(x_next, denoised, mode, low_s, double_high_s, wavelet)
