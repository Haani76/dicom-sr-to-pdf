"""Assemble the self-contained web app in _site/.

Every third-party file (the Pyodide runtime and the Python wheels) is downloaded and checked
against the SHA-256 recorded in web/vendor-lock.json. Any mismatch aborts the build, so the
published site only ever serves files that were reviewed when the lock was made.

    python web/build_site.py           # build _site/ from the lock
    python web/build_site.py --lock    # re-resolve PINS below and rewrite the lock (on upgrades)

Standard library only.
"""
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "web" / "vendor-lock.json"
CACHE = ROOT / ".vendor-cache"
SITE = ROOT / "_site"

# What the converter needs in the browser. Change these, then run --lock.
PYODIDE_VERSION = "0.27.7"
PYODIDE_CORE = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
PYODIDE_PACKAGES = ["pillow", "ssl", "html5lib", "charset-normalizer"]  # dependencies are added automatically
PYPI_PINS = ["pydicom==3.0.2", "reportlab==5.0.1", "pypdf==5.4.0", "arabic-reshaper==3.0.0", "xhtml2pdf==0.2.26"]


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def make_lock():
    base = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
    pyo_lock = json.loads(fetch(base + "pyodide-lock.json"))["packages"]
    names, todo = set(), list(PYODIDE_PACKAGES)
    while todo:  # dependency closure inside Pyodide's own package set
        n = todo.pop()
        if n not in names:
            names.add(n)
            todo += pyo_lock[n]["depends"]
    files = {}
    for f in PYODIDE_CORE + sorted(pyo_lock[n]["file_name"] for n in names):
        files[f] = {"url": base + f, "sha256": sha256(fetch(base + f))}
    wheels = {}
    for pin in PYPI_PINS:
        name, version = pin.split("==")
        meta = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
        whl = next(u for u in meta["urls"] if u["filename"].endswith("-py3-none-any.whl"))
        data = fetch(whl["url"])
        assert sha256(data) == whl["digests"]["sha256"], whl["filename"]
        wheels[whl["filename"]] = {"url": whl["url"], "sha256": whl["digests"]["sha256"]}
    LOCK.write_text(json.dumps({"pyodide_version": PYODIDE_VERSION, "pyodide": files, "wheels": wheels},
                               indent=2) + "\n", encoding="utf-8")
    print(f"wrote {LOCK.relative_to(ROOT)}: {len(files)} Pyodide files, {len(wheels)} wheels")


def verified(name, entry):
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / name
    data = cached.read_bytes() if cached.exists() else fetch(entry["url"])
    if sha256(data) != entry["sha256"]:
        cached.unlink(missing_ok=True)
        sys.exit(f"SHA-256 mismatch for {name}; refusing to build")
    cached.write_bytes(data)
    return cached


def build():
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    shutil.rmtree(SITE, ignore_errors=True)
    (SITE / "pyodide").mkdir(parents=True)
    (SITE / "wheels").mkdir()
    (SITE / "dicom_sr_to_pdf").mkdir()
    for name, entry in lock["pyodide"].items():
        shutil.copy(verified(name, entry), SITE / "pyodide" / name)
    for name, entry in lock["wheels"].items():
        shutil.copy(verified(name, entry), SITE / "wheels" / name)
    for f in ("index.html", "app.js", "worker.js"):
        shutil.copy(ROOT / "web" / f, SITE / f)
    for f in ("__init__.py", "report.py"):
        shutil.copy(ROOT / "dicom_sr_to_pdf" / f, SITE / "dicom_sr_to_pdf" / f)
    (SITE / "vendor.json").write_text(json.dumps({"wheels": list(lock["wheels"])}), encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"built {SITE.relative_to(ROOT)}/ ({size:.1f} MB), all third-party files verified")


if __name__ == "__main__":
    make_lock() if "--lock" in sys.argv else build()
