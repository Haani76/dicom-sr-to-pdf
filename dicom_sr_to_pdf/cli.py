"""Command line entry point: convert one SR file or whole folders of them."""
import argparse
import sys
from pathlib import Path

from pydicom.errors import InvalidDicomError

from . import __version__
from .report import render


def find_inputs(paths):
    """Yield input files; folders are searched recursively (DICOM files often have no extension)."""
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(f for f in p.rglob("*") if f.is_file())
        else:
            yield p


def convert(src, pdf_path, details=False, keep_html=False):
    html, pdf, missing = render(src, details)
    if missing:
        print(f"WARN  {src}: not shown in PDF: {', '.join(missing)}", file=sys.stderr)
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    if keep_html:
        Path(pdf_path).with_suffix(".html").write_text(html, encoding="utf-8")
    Path(pdf_path).write_bytes(pdf)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dicom-sr-to-pdf",
                                 description="Convert DICOM Structured Reports to PDF.")
    ap.add_argument("inputs", nargs="+", help="SR files and/or folders to convert")
    ap.add_argument("-o", "--output",
                    help="output .pdf (single input) or folder (default: next to each input)")
    ap.add_argument("--details", action="store_true",
                    help="show coding scheme codes and referenced image UIDs")
    ap.add_argument("--html", action="store_true", help="also keep the intermediate HTML")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    files = list(find_inputs(args.inputs))
    single_pdf = args.output and args.output.lower().endswith(".pdf")
    if single_pdf and len(files) != 1:
        ap.error("-o FILE.pdf needs exactly one input; pass a folder for batches")

    done = failed = skipped = 0
    for src in files:
        if single_pdf:
            dest = Path(args.output)
        else:
            dest = (Path(args.output) if args.output else src.parent) / (src.stem + ".pdf")
        try:
            convert(src, dest, args.details, args.html)
            print(f"ok    {src} -> {dest}")
            done += 1
        except (InvalidDicomError, ValueError) as e:
            # In folder scans, non-SR files (images, DICOMDIR) are expected; just skip them.
            print(f"skip  {src}: {e}", file=sys.stderr)
            skipped += 1
        except Exception as e:  # keep going so one bad file doesn't stop a batch
            print(f"FAIL  {src}: {e}", file=sys.stderr)
            failed += 1
    print(f"{done} converted, {skipped} skipped, {failed} failed")
    return 1 if failed or not done else 0


if __name__ == "__main__":
    sys.exit(main())
