"""Integration test against a real archive: set BRSAR=/path/to/file.brsar."""
import os

import numpy as np
import pytest

from brsar_sfx.extract import Options, _render_job, _worker_init, select_sounds
from brsar_sfx.rsar import Rsar

BRSAR = os.environ.get("BRSAR")
pytestmark = pytest.mark.skipif(not BRSAR, reason="set BRSAR to a .brsar file to run")


def test_render_a_few_sounds():
    with open(BRSAR, "rb") as f:
        rsar = Rsar(f.read())
    sounds = select_sounds(rsar)[:10]
    _worker_init(BRSAR, Options())
    for s in sounds:
        r = _render_job((s.index, ""))
        assert r.error is None, r.error
        assert r.pcm is not None and r.pcm.shape[1] > 0
        assert np.abs(r.pcm).max() > 0
