# DICOM SR to PDF

Converts a DICOM Structured Report (SR) into a PDF laid out like the SR view in MicroDICOM: patient/study header, teal section headers, and each measurement with its value, unit and modifiers.

## How it works

1. Reads the SR with `pydicom`.
2. Header: patient, study, protocol, manufacturer/model/serial, completion and verification flags, content date/time.
3. Walks `ContentSequence` recursively:
   - `CONTAINER` → teal section header
   - `NUM` → bold concept name, value + unit, then `Concept Modifier` / `Properties` lines (code, scheme)
   - `IMAGE` → referenced SOP Instance UID
   - `CODE` / `TEXT` / `PNAME` / `DATE` / `TIME` / `DATETIME` → `Observation Context` lines
4. Writes an HTML file and renders it to A4 PDF with `wkhtmltopdf`.

## Setup

```bash
sudo apt install wkhtmltopdf
pip install -r requirements.txt
```

## Usage

```bash
python3 build_sr_pdf.py report.dcm            # -> report.pdf (+ report.html)
python3 build_sr_pdf.py report.dcm out.pdf
```

## Notes

- Tested on Mindray vascular ultrasound SRs.
- Output contains patient data. Never commit `.dcm`, `.pdf` or `.html` outputs (excluded in `.gitignore`).
