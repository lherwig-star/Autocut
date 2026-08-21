"""Gemeinsame Testdaten: werden einmal pro Testlauf erzeugt."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autocut.ffmpeg_tools import have_ffmpeg  # noqa: E402
from tests.make_testdata import build_all  # noqa: E402

requires_ffmpeg = pytest.mark.skipif(not have_ffmpeg(), reason="ffmpeg ist nicht installiert")


@pytest.fixture(scope="session")
def testdata(tmp_path_factory):
    if not have_ffmpeg():
        pytest.skip("ffmpeg ist nicht installiert")
    folder = tmp_path_factory.mktemp("autocut_testdata")
    return build_all(str(folder))


@pytest.fixture(scope="session")
def music(testdata):
    from autocut.audio_analysis import analyze_music

    return analyze_music(testdata["music"])


@pytest.fixture(scope="session")
def clips(testdata):
    from autocut.clips import load_clips

    return load_clips(testdata["clips_dir"])


@pytest.fixture(scope="session")
def analyses(clips):
    from autocut.video_analysis import absolute_quality, analyze_clip

    result = {c.path: analyze_clip(c.path, c.info) for c in clips}
    quality = {path: absolute_quality(a) for path, a in result.items()}
    return result, quality
