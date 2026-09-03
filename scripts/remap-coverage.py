"""Remap bare container-relative filenames in a coverage.xml to repo paths.

`make test-backend` runs pytest inside Docker, which emits paths relative to
its own rootdirs (e.g. `admin/admin_router.py` for backend/src files, bare
`consumer.py` for generator/kafka files). Codecov cannot map those to repo
files, so CLI uploads silently contribute nothing. This script resolves every
filename against backend/{src,generator,kafka}:

- already repo-relative (`backend/...`) -> keep
- `a/b.py`-style -> exactly one of backend/{src,generator,kafka}/a/b.py
  must exist on disk, else abort
- bare name -> exactly one `find` hit by basename (PINNED exception below),
  else abort (live lines) or drop (zero lines, e.g. stray __init__.py)

A bad upload is worse than none: anything unresolved aborts loudly instead
of shipping a half-mapped file.

PINNED: bare config.py exists in three places; line-by-line verification
showed the measured file is backend/generator/config.py (14 exec lines,
ending at EOF 25).

Usage: remap-coverage.py <in.xml> <out.xml>
"""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET

PIN = {"config.py": "backend/generator/config.py"}
SRC = ["backend/src", "backend/generator", "backend/kafka"]


def resolve(fn: str) -> str:
    """Return the repo-relative path for fn, or '' when unresolvable."""
    if fn.startswith("backend/"):
        return fn
    if "/" in fn:
        hits = [r + "/" + fn for r in SRC if os.path.isfile(r + "/" + fn)]
        return hits[0] if len(hits) == 1 else ""
    if fn in PIN:
        return PIN[fn]
    out = subprocess.run(
        ["find"] + SRC + ["-name", fn], capture_output=True, text=True
    ).stdout.split()
    return out[0] if len(out) == 1 else ""


def main(src: str, dst: str) -> None:
    tree = ET.parse(src)
    total = hits = rewritten = kept = dropped = 0
    pairs = [(p, c) for p in tree.getroot().iter() for c in list(p) if c.tag == "class"]
    for parent, cls in pairs:
        lines = list(cls.iter("line"))
        total += len(lines)
        hits += sum(1 for ln in lines if ln.get("hits", "0") != "0")
        fn = cls.get("filename", "")
        new = resolve(fn)
        if new:
            if new != fn:
                cls.set("filename", new)
                rewritten += 1
            else:
                kept += 1
        elif not lines:
            parent.remove(cls)
            dropped += 1
        else:
            print("!! unresolvable coverage file with live lines: " + fn)
            sys.exit(1)
    for cls in tree.getroot().iter("class"):
        if not cls.get("filename", "").startswith("backend/"):
            print("!! leaked unmapped path: " + cls.get("filename", ""))
            sys.exit(1)
    tree.write(dst)
    pct = round(100.0 * hits / total, 2) if total else 0.0
    print(
        "mapped " + str(rewritten + kept) + " files (" + str(rewritten)
        + " rewritten, " + str(kept) + " already ok), dropped " + str(dropped)
        + " empty, lines " + str(hits) + "/" + str(total) + " (" + str(pct) + "%)"
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
