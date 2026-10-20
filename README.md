# dicom-sr-to-pdf

Convert DICOM Structured Reports (SR) into clean, readable A4 PDF reports. Works on single files or whole folders. Pure Python, no system dependencies.

## What the PDF looks like

- **Title** from the SR's root concept (e.g. *Vascular Ultrasound Procedure Report*)
- **Header panel**: patient, ID, sex/DOB, accession, study, study date, institution, referring physician, device, completion/verification status (empty fields are omitted)
- **Sections** for each `CONTAINER`, nested sub-sections as sub-headings
- **Measurement tables** for `NUM` items: measurement, value, unit (UCUM), qualifiers (concept modifiers and properties such as laterality)
- **Context** (`CODE`, `TEXT`, `PNAME`, `DATE`, `TIME`, `DATETIME`, `UIDREF`) as compact key/value rows
- **Footer** on every page: generation time, tool version, page *x* of *y*

Coding-scheme codes and referenced image UIDs are hidden by default; add `--details` to include them.

## Install

```bash
pip install git+https://github.com/Haani76/dicom-sr-to-pdf
```

or from a clone: `pip install .`

## Usage

```bash
dicom-sr-to-pdf report.dcm                  # -> report.pdf next to the input
dicom-sr-to-pdf report.dcm -o out/final.pdf # explicit output file
dicom-sr-to-pdf exams/ -o pdfs/             # batch: every SR under exams/, recursively
dicom-sr-to-pdf a.dcm b.dcm --details       # include codes and image UIDs
dicom-sr-to-pdf report.dcm --html           # also keep the intermediate HTML
```

`python -m dicom_sr_to_pdf ...` works too. In folder mode, files that are not DICOM SRs (images, DICOMDIR, other files) are skipped. One bad file never stops the batch. The exit code is non-zero if any file failed or nothing was converted.

## Development

```bash
pip install -e ".[test]"
pytest
```

Tests build a synthetic SR with a fake patient, so no real data is needed.

## Notes

- Tested on Mindray vascular ultrasound SRs and synthetic TID 5100-style reports.
- The PDF is a readable rendering of SR content, **not a signed clinical report**.
- Output contains patient data. Never commit `.dcm`, `.pdf` or `.html` files (they are excluded in `.gitignore`).
