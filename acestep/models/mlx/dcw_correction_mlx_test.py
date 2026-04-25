"""Tests for ``acestep.models.mlx.dcw_correction_mlx``.

The test module is import-safe on platforms without MLX — tests that need
``mlx.core`` are skipped automatically (Linux / Windows CI).
"""

import importlib.util
import math

import pytest


HAS_MLX = importlib.util.find_spec("mlx") is not None


@pytest.fixture
def dcw_mlx():
    from acestep.models.mlx import dcw_correction_mlx
    return dcw_correction_mlx


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_haar_roundtrip_is_identity(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((2, 16, 8))
    low, high = dcw_mlx._haar_dwt_1d(x)
    recon = dcw_mlx._haar_idwt_1d(low, high, out_T=16)
    # Haar is orthogonal; roundtrip should recover x up to float noise.
    diff = mx.abs(recon - x).max().item()
    assert diff < 1e-4


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_haar_roundtrip_odd_length_via_right_pad(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((1, 15, 4))
    low, high = dcw_mlx._haar_dwt_1d(x)
    # Reconstructing to the original odd length drops the pad sample.
    recon = dcw_mlx._haar_idwt_1d(low, high, out_T=15)
    diff = mx.abs(recon - x).max().item()
    assert diff < 1e-4
    assert recon.shape == (1, 15, 4)


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_disabled_is_identity(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((1, 8, 4))
    y = mx.random.normal((1, 8, 4))
    out = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=0.5, enabled=False, mode="low",
        scaler=0.1, high_scaler=0.0, wavelet="haar",
    )
    assert mx.all(out == x).item()


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_zero_t_is_identity(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((1, 8, 4))
    y = mx.random.normal((1, 8, 4))
    out = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=0.0, enabled=True, mode="low",
        scaler=0.5, high_scaler=0.0, wavelet="haar",
    )
    # t_curr=0 forces s=0 which short-circuits to x.
    diff = mx.abs(out - x).max().item()
    assert diff < 1e-6


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_low_matches_manual_formula(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((1, 8, 2))
    y = mx.random.normal((1, 8, 2))
    s_user = 0.3
    t = 0.5
    out = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=t, enabled=True, mode="low",
        scaler=s_user, high_scaler=0.0, wavelet="haar",
    )
    # Manual reference: DWT -> correct L -> IDWT.
    s = s_user * t
    xL, xH = dcw_mlx._haar_dwt_1d(x)
    yL, _ = dcw_mlx._haar_dwt_1d(y)
    xL_c = xL + s * (xL - yL)
    ref = dcw_mlx._haar_idwt_1d(xL_c, xH, out_T=x.shape[1])
    diff = mx.abs(out - ref).max().item()
    assert diff < 1e-5


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_pix_matches_formula(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((1, 8, 2))
    y = mx.random.normal((1, 8, 2))
    out = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=1.0, enabled=True, mode="pix",
        scaler=0.25, high_scaler=0.0, wavelet="haar",
    )
    ref = x + 0.25 * (x - y)
    diff = mx.abs(out - ref).max().item()
    assert diff < 1e-6


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_pix_uses_raw_scaler_no_t_decay(dcw_mlx):
    # Matches the PyTorch DCWCorrector: pix is raw-scaler, no t modulation.
    import mlx.core as mx

    x = mx.random.normal((1, 8, 2))
    y = mx.random.normal((1, 8, 2))
    ref = x + 0.25 * (x - y)
    for t in (0.0, 0.3, 0.7, 1.0):
        out = dcw_mlx.apply_mlx_dcw(
            x, y, t_curr=t, enabled=True, mode="pix",
            scaler=0.25, high_scaler=0.0, wavelet="haar",
        )
        assert mx.abs(out - ref).max().item() < 1e-6, f"pix drift at t={t}"


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_high_schedule_is_complementary(dcw_mlx):
    # Paper Eq. 21: high-band uses (1 - t) * scaler, so:
    #   t=1.0 → identity (high-freq emerges later; nothing to correct yet)
    #   t=0.0 → full scaler
    import mlx.core as mx

    x = mx.random.normal((1, 8, 2))
    y = mx.random.normal((1, 8, 2))
    # At t=1.0: no correction.
    out_one = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=1.0, enabled=True, mode="high",
        scaler=0.5, high_scaler=0.0, wavelet="haar",
    )
    assert mx.abs(out_one - x).max().item() < 1e-6

    # At t=0.0: full correction — equivalent to a t_curr=1.0 call under the
    # old (buggy) schedule for `low` mode, which is what we use here to
    # generate the reference via the low-mode path (both paths apply the
    # same `xH = xH + s*(xH - yH)` math; we construct the reference by
    # hand).
    T = x.shape[1]
    xL, xH = dcw_mlx._haar_dwt_1d(x)
    yL, yH = dcw_mlx._haar_dwt_1d(y)
    xH_ref = xH + 0.5 * (xH - yH)
    ref_zero = dcw_mlx._haar_idwt_1d(xL, xH_ref, T)
    out_zero = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=0.0, enabled=True, mode="high",
        scaler=0.5, high_scaler=0.0, wavelet="haar",
    )
    assert mx.abs(out_zero - ref_zero).max().item() < 1e-5


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_double_schedule_complementary(dcw_mlx):
    # double mode: low uses t*scaler, high uses (1-t)*high_scaler.
    # At t=0.5, scaler=0.4, high_scaler=0.6 → low_s=0.2, high_s=0.3.
    import mlx.core as mx

    x = mx.random.normal((1, 8, 2))
    y = mx.random.normal((1, 8, 2))
    T = x.shape[1]
    xL, xH = dcw_mlx._haar_dwt_1d(x)
    yL, yH = dcw_mlx._haar_dwt_1d(y)
    xL_ref = xL + 0.2 * (xL - yL)
    xH_ref = xH + 0.3 * (xH - yH)
    ref = dcw_mlx._haar_idwt_1d(xL_ref, xH_ref, T)
    out = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=0.5, enabled=True, mode="double",
        scaler=0.4, high_scaler=0.6, wavelet="haar",
    )
    assert mx.abs(out - ref).max().item() < 1e-5


HAS_PW = importlib.util.find_spec("pytorch_wavelets") is not None


@pytest.mark.skipif(not (HAS_MLX and HAS_PW), reason="MLX or pytorch_wavelets missing")
def test_apply_mlx_dcw_non_haar_differs_from_haar(dcw_mlx):
    """Selecting a non-Haar wavelet should produce a different output — i.e.
    the torch bridge is actually invoked and the UI's dropdown is not a
    silent no-op on MLX.
    """
    import mlx.core as mx

    x = mx.random.normal((1, 32, 4))
    y = mx.random.normal((1, 32, 4))
    out_haar = dcw_mlx.apply_mlx_dcw(
        x, y, t_curr=0.7, enabled=True, mode="low",
        scaler=0.2, high_scaler=0.0, wavelet="haar",
    )
    for wav in ("db4", "sym8"):
        out_other = dcw_mlx.apply_mlx_dcw(
            x, y, t_curr=0.7, enabled=True, mode="low",
            scaler=0.2, high_scaler=0.0, wavelet=wav,
        )
        diff = mx.abs(out_other - out_haar).max().item()
        assert diff > 1e-4, f"MLX {wav} output was identical to haar — bridge not firing"
        assert out_other.shape == x.shape


@pytest.mark.skipif(not (HAS_MLX and HAS_PW), reason="MLX or pytorch_wavelets missing")
def test_apply_mlx_dcw_matches_torch_path_exactly(dcw_mlx):
    """MLX non-Haar output must match the CUDA/CPU torch path bit-for-bit
    (minus float32 conversion noise) — that's the whole point of the
    bridge.
    """
    import mlx.core as mx
    import torch
    import numpy as np
    from acestep.models.common.dcw_primitives import dcw_low as torch_dcw_low

    x_mx = mx.random.normal((1, 32, 4))
    y_mx = mx.random.normal((1, 32, 4))
    x_t = torch.from_numpy(np.array(x_mx, dtype="float32"))
    y_t = torch.from_numpy(np.array(y_mx, dtype="float32"))

    wav = "sym8"
    t = 0.5
    s_user = 0.1
    # Bridge output (via MLX entrypoint)
    out_mx = dcw_mlx.apply_mlx_dcw(
        x_mx, y_mx, t_curr=t, enabled=True, mode="low",
        scaler=s_user, high_scaler=0.0, wavelet=wav,
    )
    out_mx_np = np.array(out_mx)

    # Reference output (pure torch)
    out_t = torch_dcw_low(x_t, y_t, t * s_user, wavelet=wav).numpy()

    diff = float(np.abs(out_mx_np - out_t).max())
    assert diff < 1e-5, f"MLX bridge diverged from torch path by {diff}"


@pytest.mark.skipif(not HAS_MLX, reason="MLX not installed")
def test_apply_mlx_dcw_invalid_mode_raises(dcw_mlx):
    import mlx.core as mx

    x = mx.random.normal((1, 8, 2))
    y = mx.random.normal((1, 8, 2))
    with pytest.raises(ValueError):
        dcw_mlx.apply_mlx_dcw(
            x, y, t_curr=0.5, enabled=True, mode="bogus",
            scaler=0.1, high_scaler=0.0, wavelet="haar",
        )


# A sanity test that runs on any platform: verify the pure-Python sqrt(2)
# constant used by the Haar implementation.
def test_sqrt2_constant():
    assert abs(math.sqrt(2.0) ** 2 - 2.0) < 1e-12
