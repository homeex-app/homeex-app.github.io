"""Copy the Google Drive images used by Home Ex into img/ so the site serves them itself.

Reads the public exercises and settings from Firestore, downloads every Drive image
that is not copied yet, saves it as a smaller .webp and updates img/map.json
(Drive file id -> file name). The site uses the copy when it exists, otherwise Drive.
Runs every night from .github/workflows/copy-images.yml, or by hand:
    python tools/copy_images.py
"""
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "img"
MAP = IMG / "map.json"
PROJECT = "homeex-b938a"
SITE = "https://homeex-app.github.io/"
MAX_SIDE = 1400
UA = "Mozilla/5.0 (HomeEx image copier)"


def api_key():
    m = re.search(r'apiKey:"([^"]+)"', (ROOT / "index.html").read_text(encoding="utf-8"))
    return m.group(1)


def get_json(url):
    req = urllib.request.Request(url, headers={"Referer": SITE, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def strings(value):
    """All string values inside a Firestore REST value."""
    if "stringValue" in value:
        yield value["stringValue"]
    for v in value.get("arrayValue", {}).get("values", []):
        yield from strings(v)
    for v in value.get("mapValue", {}).get("fields", {}).values():
        yield from strings(v)


def drive_id(url):
    if "drive.google.com" not in url:
        return None
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", url) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def used_ids(key):
    base = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
    ids = []
    token = ""
    while True:
        q = {"pageSize": 300, "key": key}
        if token:
            q["pageToken"] = token
        d = get_json(f"{base}/exercises?{urllib.parse.urlencode(q)}")
        for doc in d.get("documents", []):
            for url in strings(doc["fields"].get("images", {})):
                ids.append(drive_id(url))
        token = d.get("nextPageToken")
        if not token:
            break
    s = get_json(f"{base}/settings/main?key={key}")["fields"]
    for field in ("heroImages", "adImages"):
        for url in strings(s.get(field, {})):
            ids.append(drive_id(url))
    return list(dict.fromkeys(i for i in ids if i))


def download(fid):
    url = f"https://drive.google.com/thumbnail?id={fid}&sz=w1600"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    im.save(out, "WEBP", quality=80, method=6)
    return out.getvalue()


def main():
    IMG.mkdir(exist_ok=True)
    mapping = json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}
    ids = used_ids(api_key())
    todo = [i for i in ids if i not in mapping or not (IMG / mapping[i]).exists()]
    print(f"{len(ids)} images used, {len(todo)} to copy")
    failed = 0
    for n, fid in enumerate(todo, 1):
        for attempt in range(3):
            try:
                (IMG / f"{fid}.webp").write_bytes(download(fid))
                mapping[fid] = f"{fid}.webp"
                print(f"[{n}/{len(todo)}] {fid} ok")
                break
            except Exception as e:  # Drive sometimes refuses; try again later
                if attempt == 2:
                    failed += 1
                    print(f"[{n}/{len(todo)}] {fid} FAILED: {e}")
                else:
                    time.sleep(3 * (attempt + 1))
        time.sleep(0.4)
    MAP.write_text(json.dumps(dict(sorted(mapping.items())), indent=0), encoding="utf-8")
    print(f"done, {failed} failed (they stay on Drive until the next run)")


if __name__ == "__main__":
    sys.exit(main())
