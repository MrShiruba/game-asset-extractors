import numpy as np

from brsar_sfx import dsp


def _snr(x, y):
    x = x.astype(float)
    y = y.astype(float)
    return 10 * np.log10((x ** 2).sum() / max(((x - y) ** 2).sum(), 1e-9))


def test_roundtrip_sine():
    t = np.arange(32000) / 32000
    x = (np.sin(2 * np.pi * 440 * t) * 12000).astype(np.int16)
    e = dsp.encode_many([x])[0]
    assert len(e.data) == (len(x) + 13) // 14 * 8
    y = dsp.decode(e.data, 0, e.num_samples, list(e.coefs))
    assert _snr(x, y) > 40


def test_roundtrip_noise_and_silence():
    rng = np.random.default_rng(1)
    noise = (rng.normal(size=20000) * 4000).astype(np.int16)
    silence = np.zeros(1000, dtype=np.int16)
    e1, e2 = dsp.encode_many([noise, silence])
    assert _snr(noise, dsp.decode(e1.data, 0, e1.num_samples, list(e1.coefs))) > 18
    assert not dsp.decode(e2.data, 0, e2.num_samples, list(e2.coefs)).any()


def test_block_history_matches_decoder():
    t = np.arange(40000) / 32000
    x = (np.sin(2 * np.pi * 220 * t) * 8000).astype(np.int16)
    e = dsp.encode_many([x], block_samples=0x3800)[0]
    y = dsp.decode(e.data, 0, e.num_samples, list(e.coefs))
    assert e.block_history[0] == (0, 0)
    # history at block 1 = last two decoded samples of block 0
    assert e.block_history[1] == (int(y[0x3800 - 1]), int(y[0x3800 - 2]))


def test_nibble_address():
    assert dsp.nibble_to_sample(2) == 0
    assert dsp.nibble_to_sample(18) == 14
