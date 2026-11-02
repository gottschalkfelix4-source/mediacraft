"""Remote path mappings: whitespace pasted along with a path must not make the mapping miss."""
import os

from app.db import session_scope
from app.downloadclients.manager import map_path
from app.models import DownloadClient, RemotePathMapping


def test_mapping_with_stray_whitespace_still_applies():
    with session_scope() as db:
        client = DownloadClient(name="SAB", kind="sabnzbd", host="192.168.188.129")
        db.add(client)
        db.add(RemotePathMapping(host=" * ", remote_path=" /config/Downloads/complete ",
                                 local_path="/data/work/appdata/sabvpn/Downloads/complete "))
        db.flush()
        mapped = map_path(db, client, "/config/Downloads/complete/Show.S02E05/Show.S02E05.mkv")
        assert mapped == os.path.join("/data/work/appdata/sabvpn/Downloads/complete", "Show.S02E05", "Show.S02E05.mkv")
        db.rollback()
