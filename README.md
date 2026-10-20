# dicom-sr-to-pdf

Convert DICOM Structured Reports (SR) into clean, readable A4 PDF reports. Works on single files or whole folders. Pure Python, no system dependencies.

## What the PDF looks like

- **Title** from the SR's root concept (e.g. *Vascular Ultrasound Procedure Report*)
- **Header panel**: patient, ID, sex/DOB, accession, study, study ID, protocol, study date, institution, department, referring/performing physician, operator, device, serial number, software version, completion/verification status (empty fields are omitted)
- **Sections** for each `CONTAINER`, nested sub-sections as sub-headings
- **Measurement tables** for `NUM` items: measurement, value, unit (UCUM), qualifiers (concept modifiers and properties such as laterality)
- **Every other item** (`CODE`, `TEXT`, `PNAME`, `DATE`, `TIME`, `DATETIME`, `UIDREF`, `SCOORD`, `SCOORD3D`, `TCOORD`, `COMPOSITE`, `WAVEFORM`, by-reference items) as key/value rows, with everything nested under it listed below
- **Referenced images/objects** summarised per section
- **Footer** on every page: generation time, tool version, page *x* of *y*

By default a reading repeated with the same name and value (e.g. Mindray's raw value followed by its "mean value chosen" copy) is shown once, and coding-scheme codes, image UIDs and coordinates are hidden. `--details` shows all of it, plus an appendix with every DICOM attribute outside the report tree.

### Nothing is dropped silently

After rendering, every concept name and value in the SR is checked against the output. Anything not in the PDF (e.g. a value type newer than this tool) is printed as a `WARN` line naming it.

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
