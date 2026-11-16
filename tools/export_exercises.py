"""Save all public exercises into data/exercises.json so the site loads them from GitHub
instead of reading every exercise from Firestore (saves the free Firestore quota).

The file carries the exercises version (settings/main.exVersion). The site uses the file
only when its version matches the live one; otherwise it falls back to Firestore.
Runs every 15 minutes from .github/workflows/export-exercises.yml (does nothing when the
version did not change), or by hand:
    python tools/export_exercises.py
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "exercises.json"
PROJECT = "homeex-b938a"
SITE = "https://homeex-app.github.io/"
UA = "Mozilla/5.0 (HomeEx exercises export)"
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
DROP = {"createdAt", "updatedAt"}


def api_key():
    m = re.search(r'apiKey:"([^"]+)"', (ROOT / "index.html").read_text(encoding="utf-8"))
    return m.group(1)


def get_json(url):
    req = urllib.request.Request(url, headers={"Referer": SITE, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def plain(v):
    """Firestore REST value -> plain JSON value (same shape the web SDK gives)."""
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "booleanValue" in v:
        return v["booleanValue"]
    if "nullValue" in v:
        return None
    if "arrayValue" in v:
        return [plain(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {k: plain(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "timestampValue" in v:
        return v["timestampValue"]
    return None


def main():
    key = api_key()
    settings = get_json(f"{BASE}/settings/main?key={key}&mask.fieldPaths=exVersion")
    version = plain(settings.get("fields", {}).get("exVersion", {"integerValue": "0"})) or 0
    version = int(version)
    old = None
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            old = None
    if old and old.get("v") == version and version and "--force" not in sys.argv:
        print(f"up to date (version {version})")
        return
    items, token = [], ""
    while True:
        url = f"{BASE}/exercises?key={key}&pageSize=300" + (f"&pageToken={token}" if token else "")
        page = get_json(url)
        for d in page.get("documents", []):
            ex = {k: plain(x) for k, x in d.get("fields", {}).items() if k not in DROP}
            ex["id"] = d["name"].rsplit("/", 1)[1]
            items.append(ex)
        token = page.get("nextPageToken", "")
        if not token:
            break
    if not items:
        print("no exercises read; keeping the old file")
        sys.exit(1)
    items.sort(key=lambda e: (e.get("number") if isinstance(e.get("number"), (int, float)) else 10**9, e["id"]))
    if old and old.get("v") == version and old.get("list") == items:
        print(f"no change (version {version})")
        return
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"v": version, "at": int(time.time() * 1000), "list": items},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"saved {len(items)} exercises (version {version}) -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
