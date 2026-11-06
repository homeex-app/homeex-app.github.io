"""Build lang/<code>.json from the translation sources in lang/src/.

Each source file (lang/src/<code>.txt, <code>.2.txt, ...) has one block per exercise:
    @<exercise number>
    <name>
    <description lines...>
The site loads lang/<code>.json only for the language a patient's program is sent in.
Run:  python tools/build_lang.py
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "lang" / "src"
OUT = ROOT / "lang"
PROJECT = "homeex-b938a"
SITE = "https://homeex-app.github.io/"


def number_to_id():
    key = re.search(r'apiKey:"([^"]+)"', (ROOT / "index.html").read_text(encoding="utf-8")).group(1)
    base = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents/exercises"
    ids, token = {}, ""
    while True:
        q = {"pageSize": 300, "key": key, "mask.fieldPaths": "number"}
        if token:
            q["pageToken"] = token
        req = urllib.request.Request(f"{base}?{urllib.parse.urlencode(q)}", headers={"Referer": SITE})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        for doc in d.get("documents", []):
            num = list(doc.get("fields", {}).get("number", {"x": ""}).values())[0]
            if str(num).strip():
                ids[int(num)] = doc["name"].rsplit("/", 1)[1]
        token = d.get("nextPageToken")
        if not token:
            return ids


def parse(code):
    files = [SRC / f"{code}.txt"] + sorted(SRC.glob(f"{code}.*.txt"))
    out = {}
    for f in files:
        if not f.exists():
            continue
        for block in re.split(r"^@", f.read_text(encoding="utf-8"), flags=re.M)[1:]:
            lines = block.rstrip().split("\n")
            num = int(lines[0].strip())
            out[num] = {"n": lines[1].strip(), "d": "\n".join(lines[2:]).strip()}
    return out


def main():
    ids = number_to_id()
    codes = sorted({p.name.split(".")[0] for p in SRC.glob("*.txt")})
    # Screen texts (buttons, titles) for every language: lang/src/ui.json {key: {code: text}}
    ui_src = json.loads((SRC / "ui.json").read_text(encoding="utf-8"))
    ok = True
    for code in codes:
        ui = {k: v[code] for k, v in ui_src.items() if v.get(code)}
        missing_ui = [k for k, v in ui_src.items() if not v.get(code)]
        if missing_ui:
            print(f"{code}: screen texts missing {missing_ui}")
        items = parse(code)
        missing = sorted(set(ids) - set(items))
        unknown = sorted(set(items) - set(ids))
        empty = [n for n, x in items.items() if not x["n"] or not x["d"]]
        ex = {ids[n]: items[n] for n in sorted(items) if n in ids}
        (OUT / f"{code}.json").write_text(json.dumps({"ui": ui, "ex": ex}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{code}: {len(ex)}/{len(ids)} exercises", f"missing {missing}" if missing else "", f"unknown {unknown}" if unknown else "", f"empty {empty}" if empty else "")
        ok = ok and not unknown and not empty
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
