from brsar_sfx import player


def test_release_rates_match_runtime():
    assert player.calc_release(127) == 65535.0
    assert player.calc_release(126) == 24.0
    assert abs(player.calc_release(0) - 1 / 640) < 1e-12
    assert abs(player.calc_release(120) - 2.0) < 1e-12


def test_volume_and_pitch():
    assert player.volume_ratio(0.0) == 1.0
    assert player.volume_ratio(-90.4) == 0.0
    assert abs(player.volume_ratio(-6.0) - 0.501187) < 1e-5
    assert abs(player.pitch_ratio(12) - 2.0) < 1e-9


def test_pan_sqrt_curve():
    # NW4R default curve: -3 dB in the centre, full level on the hard side
    assert abs(player.pan_ratio(0.0, 0) - 0.7071) < 1e-3
    assert player.pan_ratio(-1.0, 0) == 1.0
    assert player.pan_ratio(1.0, 0) == 0.0
