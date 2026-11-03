"""Probing real stream info and extracting packed downloads."""
import shutil
import subprocess
import zipfile

import pytest

from app.core import mediainfo
from app.services import unpack


def test_mediainfo_json_parsing():
    data = {"media": {"track": [
        {"@type": "General", "Duration": "5400.5", "OverallBitRate": "8000000"},
        {"@type": "Video", "Format": "HEVC", "Width": "3840", "Height": "1600", "HDR_Format": "Dolby Vision / SMPTE ST 2086"},
        {"@type": "Audio", "Format": "E-AC-3", "Channels": "6", "Language": "de"},
        {"@type": "Audio", "Format": "DTS", "Channels": "8", "Language": "en"},
        {"@type": "Text", "Language": "de"}]}}
    info = mediainfo._from_mediainfo(data)
    assert info["video_codec"] == "x265" and info["hdr"] == "DV" and info["duration_min"] == 90.0
    assert mediainfo._resolution(info["width"], info["height"]) == 2160
    assert [mediainfo.language(a["language"]) for a in info["audio_tracks"]] == ["german", "english"]
    assert mediainfo._resolution(1920, 800) == 1080


def test_apply_flags_mislabelled_release():
    from app.models import MediaFile

    mf = MediaFile(languages=["german", "english"], media_info={})
    probe = {"video_codec": "x264", "hdr": None, "audio_tracks": [{"codec": "AC3", "channels": 6, "language": "eng"}],
             "audio_languages": ["english"]}
    mediainfo.apply(mf, probe)
    assert mf.languages == ["english"]
    assert mf.media_info["language_mismatch"] == ["german", "english"]
    assert mf.media_info["probed"] is True


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg nicht installiert")
def test_ffprobe_real_file(tmp_root):
    out = tmp_root / "probe.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=5:duration=1",
                    "-f", "lavfi", "-i", "sine=duration=1", "-f", "lavfi", "-i", "sine=duration=1",
                    "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-c:a", "aac",
                    "-metadata:s:a:0", "language=ger", "-metadata:s:a:1", "language=eng", str(out)], check=True)
    info = mediainfo.probe(str(out))
    assert info and info["resolution"] == 720 and info["video_codec"] == "x264"
    assert info["audio_languages"] == ["german", "english"]


def test_first_volumes_and_zip_unpack(tmp_root):
    d = tmp_root / "dl" / "Film.2020.German.1080p-GRP"
    d.mkdir(parents=True)
    for n in ("film.part01.rar", "film.part02.rar", "other.rar", "other.r00", "sample.rar", "x.7z.001", "x.7z.002"):
        (d / n).write_bytes(b"x")
    names = sorted(p.split("\\")[-1].split("/")[-1] for p in unpack.first_volumes(str(d)))
    assert names == ["film.part01.rar", "other.rar", "x.7z.001"]

    z = tmp_root / "dl" / "Zipped"
    z.mkdir()
    with zipfile.ZipFile(z / "movie.zip", "w") as zf:
        zf.writestr("Movie.2020.1080p.mkv", b"\0" * 2048)
    dest = unpack.unpack(str(z))
    assert dest and any(p.name == "Movie.2020.1080p.mkv" for p in (z / unpack.UNPACK_DIR).rglob("*"))
    unpack.cleanup(dest)
    assert not (z / unpack.UNPACK_DIR).exists() and (z / "movie.zip").exists()
