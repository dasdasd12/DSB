import math

import numpy as np


PWM_PERIOD_TICKS = 2500

MODE_LEGACY_SRAM = "legacy_sram"
MODE_DSB_AM = "dsb_am"
MODE_SSB_USB = "ssb_usb"
MODE_SSB_LSB = "ssb_lsb"
MODE_MAM1 = "mam1"
MODULATION_MODES = (MODE_LEGACY_SRAM, MODE_DSB_AM, MODE_SSB_USB, MODE_SSB_LSB, MODE_MAM1)


def normalize_audio(samples):
    x = np.asarray(samples, dtype=float)
    if x.size == 0:
        return x
    peak = max(float(np.max(np.abs(x))), 1.0)
    if peak > 1.0:
        x = x / peak
    return np.clip(x, -1.0, 1.0)


def hilbert_transform(samples):
    x = np.asarray(samples, dtype=float)
    n = len(x)
    if n == 0:
        return x.copy()
    spectrum = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = 1.0
        h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[0] = 1.0
        h[1:(n + 1) // 2] = 2.0
    analytic = np.fft.ifft(spectrum * h)
    return np.imag(analytic)


def iq_for_mode(samples, mode=MODE_MAM1, mod_index=0.6):
    x = normalize_audio(samples)
    m = float(max(0.0, min(1.0, mod_index)))

    if mode == MODE_DSB_AM:
        return 1.0 + m * x, np.zeros_like(x)
    if mode == MODE_SSB_USB:
        return 1.0 + m * x, m * hilbert_transform(x)
    if mode == MODE_SSB_LSB:
        return 1.0 + m * x, -m * hilbert_transform(x)
    if mode == MODE_MAM1:
        return 1.0 + m * x, 1.0 - 0.5 * m * m * x * x
    if mode == MODE_LEGACY_SRAM:
        return np.sqrt(np.maximum(0.0, 1.0 + m * x)), np.zeros_like(x)
    raise ValueError("unknown modulation mode: %s" % mode)


def polar_reference(samples, mode=MODE_MAM1, mod_index=0.6, envelope_scale_q8=256):
    i_val, q_val = iq_for_mode(samples, mode=mode, mod_index=mod_index)
    envelope = np.sqrt(i_val * i_val + q_val * q_val)
    max_env = max(float(np.max(envelope)), 1e-12)
    envelope_norm = np.clip(envelope / max_env, 0.0, 1.0)
    envelope_q12 = np.rint(envelope_norm * 4095.0 * float(envelope_scale_q8) / 256.0).astype(int)
    envelope_q12 = np.clip(envelope_q12, 0, 4095)
    phase = np.mod(np.arctan2(q_val, i_val), 2.0 * math.pi)
    phase_ticks = np.rint(phase * PWM_PERIOD_TICKS / (2.0 * math.pi)).astype(int) % PWM_PERIOD_TICKS
    return envelope_q12.tolist(), phase_ticks.tolist()
