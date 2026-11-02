import pytest

from app.core.parser import parse, normalize_title, parse_path


@pytest.mark.parametrize("name,title,year,quality,langs,group", [
    ("The.Matrix.1999.1080p.BluRay.x264-SPARKS", "The Matrix", 1999, "Bluray-1080p", ["english"], "SPARKS"),
    ("Der.Pate.1972.German.DL.1080p.BluRay.x264-DETAiLS", "Der Pate", 1972, "Bluray-1080p", ["german", "english"], "DETAiLS"),
    ("Dune.Part.Two.2024.German.DL.2160p.UHD.BluRay.HDR.DV.x265-GROUP", "Dune Part Two", 2024, "Bluray-2160p", ["german", "english"], "GROUP"),
    ("Oppenheimer.2023.2160p.UHD.BluRay.REMUX.DV.HDR.HEVC.TrueHD.Atmos.7.1-FGT", "Oppenheimer", 2023, "Remux-2160p", ["english"], "FGT"),
    ("2001.A.Space.Odyssey.1968.720p.BluRay.x264-AMIABLE", "2001 A Space Odyssey", 1968, "Bluray-720p", ["english"], "AMIABLE"),
    ("Blade Runner 2049 (2017) 1080p WEB-DL DD5.1 H264-FGT", "Blade Runner 2049", 2017, "WEBDL-1080p", ["english"], "FGT"),
    ("Some.Movie.2021.German.AC3.WEBRip.x264-LeetXD", "Some Movie", 2021, "WEBRip-480p", ["german"], "LeetXD"),
    ("Movie.Title.2020.MULTi.1080p.WEB.H264-GRP", "Movie Title", 2020, "WEBDL-1080p", ["english", "multi"], "GRP"),
    ("Film.2019.German.Subbed.720p.WEB.h264-ABC", "Film", 2019, "WEBDL-720p", ["english"], "ABC"),
])
def test_movies(name, title, year, quality, langs, group):
    p = parse(name)
    assert not p.is_tv
    assert p.title == title
    assert p.year == year
    assert p.quality == quality
    assert p.languages == langs
    assert p.release_group == group


@pytest.mark.parametrize("name,title,seasons,episodes,quality", [
    ("Breaking.Bad.S05E14.720p.HDTV.x264-IMMERSE", "Breaking Bad", [5], [14], "HDTV-720p"),
    ("The.Office.US.S02E01E02.1080p.WEB-DL.DD5.1.H.264-NTb", "The Office US", [2], [1, 2], "WEBDL-1080p"),
    ("Show.Name.S01E01-E03.1080p.WEB.h264-GRP", "Show Name", [1], [1, 2, 3], "WEBDL-1080p"),
    ("Show.Name.S01E05-06.German.DL.1080p.WEB.h264-GRP", "Show Name", [1], [5, 6], "WEBDL-1080p"),
    ("Dark.S01.German.DL.1080p.NF.WEBRip.x264-GRP", "Dark", [1], [], "WEBRip-1080p"),
    ("Babylon.Berlin.Staffel.2.German.720p.HDTV.x264-ABC", "Babylon Berlin", [2], [], "HDTV-720p"),
    ("Friends.S01-S10.COMPLETE.1080p.BluRay.x265-GRP", "Friends", list(range(1, 11)), [], "Bluray-1080p"),
    ("Doctor.Who.2005.S13E01.1080p.WEB.h264-GRP", "Doctor Who", [13], [1], "WEBDL-1080p"),
    ("Stargate.SG-1.1x05.DVDRip.XviD", "Stargate SG-1", [1], [5], "DVD"),
    ("Tatort.S2024E12.German.1080p.WEB.h264-GRP", "Tatort", [2024], [12], "WEBDL-1080p"),
])
def test_tv(name, title, seasons, episodes, quality):
    p = parse(name)
    assert p.is_tv
    assert p.title == title
    assert p.seasons == seasons
    assert p.episodes == episodes
    assert p.quality == quality


def test_full_season_flag():
    assert parse("Dark.S01.German.DL.1080p.NF.WEBRip.x264-GRP").full_season


def test_daily():
    p = parse("The.Daily.Show.2024.03.14.Guest.Name.720p.WEB.h264-GRP")
    assert p.is_tv and p.air_date == "2024-03-14" and p.title == "The Daily Show"


def test_anime():
    p = parse("[SubsPlease] Frieren - 12 (1080p) [ABCDEF12].mkv")
    assert p.is_tv and p.is_anime
    assert p.title == "Frieren"
    assert p.absolute_episodes == [12]
    assert p.release_group == "SubsPlease"
    assert p.resolution == 1080
    assert p.crc == "ABCDEF12"


def test_anime_version():
    p = parse("[Group] One Piece - 1085v2 [720p].mkv")
    assert p.absolute_episodes == [1085] and p.revision == 1


def test_proper_repack():
    assert parse("Show.S01E01.PROPER.720p.HDTV.x264-GRP").revision == 1
    assert parse("Show.S01E01.REPACK.PROPER.720p.HDTV.x264-GRP").revision == 2


def test_edition_hdr_audio():
    p = parse("Aliens.1986.Special.Edition.2160p.UHD.BluRay.HDR10.DTS-HD.MA.5.1.x265-GRP")
    assert p.edition == "Special Edition"
    assert "HDR10" in p.hdr
    assert "DTS-HD MA" in p.audio
    assert p.audio_channels == "5.1"
    assert p.codec == "x265"
    assert p.title == "Aliens"


def test_normalize():
    assert normalize_title("Die Schöne und das Biest") == normalize_title("Die.Schoene.und.das.Biest".replace(".", " "))
    assert normalize_title("The Office") == normalize_title("Office")
    assert normalize_title("Marvel's Agents of S.H.I.E.L.D.") == "marvelsagentsofshield"


def test_parse_path_obfuscated():
    p = parse_path("/data/torrents/Show.Name.S02E03.1080p.WEB.h264-GRP/abcdef123456.mkv")
    assert p.title == "Show Name" and p.episodes == [3] and p.quality == "WEBDL-1080p"
