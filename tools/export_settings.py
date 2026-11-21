"""Save the site settings (settings/main) into data/settings.json so phones load them from
GitHub instead of reading the big settings document from Firestore on every open
(saves the free Firestore download quota, 10 GB a month).

The tiny doc settings/ver holds the settings version `s` (the Admin page bumps it on every save).
The file carries that version; the site uses the file only when it matches.
Runs from .github/workflows/export-exercises.yml, or by hand:
    python tools/export_settings.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_exercises import BASE, ROOT, api_key, get_json, plain  # noqa: E402

OUT = ROOT / "data" / "settings.json"
DROP = {"createdAt", "updatedAt"}


def main():
    key = api_key()
    try:
        ver = get_json(f"{BASE}/settings/ver?key={key}")
    except Exception as e:  # 404 until the admin opens the site once
        print(f"no settings/ver yet ({e}); nothing to do")
        return
    s = int(plain(ver.get("fields", {}).get("s", {"integerValue": "0"})) or 0)
    if not s:
        print("settings/ver has no version yet")
        return
    old = None
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            old = None
    if old and old.get("s") == s and "--force" not in sys.argv:
        print(f"up to date (version {s})")
        return
    main_doc = get_json(f"{BASE}/settings/main?key={key}")
    d = {k: plain(x) for k, x in main_doc.get("fields", {}).items() if k not in DROP}
    if not d:
        print("settings/main is empty; keeping the old file")
        sys.exit(1)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"s": s, "at": int(time.time() * 1000), "d": d},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"saved settings (version {s}) -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
