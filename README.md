# dicom-sr-to-pdf

Turn DICOM Structured Reports (SR), the measurement reports that ultrasound, CT, MR and other imaging machines save, into clean, readable A4 PDF reports. Works on single files or whole folders. Pure Python, no system dependencies.

## ▶ Use it online, no install

**<https://haani76.github.io/dicom-sr-to-pdf/>**

Drop one SR file, several, or a whole exam folder. Within seconds you get PDFs to view in the browser or download, individually or as a zip. **Your files never leave your computer:** the converter runs inside your browser.

Prefer the command line, or need to automate?

```bash
pip install git+https://github.com/Haani76/dicom-sr-to-pdf
dicom-sr-to-pdf report.dcm          # -> report.pdf
```

---

## Contents

- [The problem this solves](#the-problem-this-solves)
- [Background: what is DICOM?](#background-what-is-dicom)
- [Background: what is a DICOM Structured Report?](#background-what-is-a-dicom-structured-report)
- [What the tool does](#what-the-tool-does)
- [Who it is for](#who-it-is-for)
- [The web app](#the-web-app)
- [Installation](#installation)
- [Usage](#usage)
- [What the PDF contains](#what-the-pdf-contains)
- [Default view vs `--details`](#default-view-vs---details)
- [Completeness check and warnings](#completeness-check-and-warnings)
- [Batch conversion](#batch-conversion)
- [Exit codes](#exit-codes)
- [Using it from Python](#using-it-from-python)
- [How it works internally](#how-it-works-internally)
- [Privacy and patient data](#privacy-and-patient-data)
- [Limitations](#limitations)
- [Troubleshooting / FAQ](#troubleshooting--faq)
- [Development](#development)
- [Versions and rolling back](#versions-and-rolling-back)
- [Hosting your own copy of the web app](#hosting-your-own-copy-of-the-web-app)
- [Security and privacy (HIPAA)](SECURITY_AND_PRIVACY.md)
- [Glossary](#glossary)

---

## The problem this solves

Modern imaging machines don't just save pictures. During an exam the operator takes measurements on screen, such as vessel diameters, flow velocities, reflux times, heart chamber sizes or organ volumes. The machine stores them in a **DICOM Structured Report**: a file that sits next to the images in the study and holds every measurement in a coded, machine-readable form.

That format is good for software and bad for people:

- **You cannot open it like a document.** Double-clicking a `.dcm` SR does nothing useful. You need a DICOM viewer (MicroDicom, Horos, OsiriX, a PACS workstation), and many free viewers show SRs badly or not at all.
- **What viewers show is raw.** Even good viewers render the SR as a long dump: every value repeated, coding-scheme codes like `(121401, DCM)` on every line, numbers like `1267.500000`, image UIDs 60 characters long.
- **It can't be shared easily.** Referring doctors, patients, insurers, auditors and researchers usually want a PDF they can open anywhere, print, attach to an email or archive.
- **Doing it by hand doesn't scale.** Copying 100+ measurements from a viewer into a report template is slow and error-prone.

**dicom-sr-to-pdf** reads the SR file directly and produces a tidy, paginated PDF report with a patient/study header, sections, and measurement tables. It needs no viewer, no PACS and no manual copying, and it checks that nothing in the SR was left out.

---

## Background: what is DICOM?

**DICOM** (*Digital Imaging and Communications in Medicine*) is the international standard for medical imaging data. Practically every scanner, ultrasound machine, X-ray system, PACS (image archive) and radiology workstation in the world speaks it. It defines two things:

1. **A file format.** A DICOM file (`.dcm`, often with no extension at all) is a list of *attributes* (also called *tags* or *data elements*). Each attribute has a numeric tag like `(0010,0010)`, a name like `PatientName`, a data type (the *VR*: date, text, number, person name, sequence...) and a value. One file usually holds one *object*: one image or one report.
2. **A network protocol** for sending, querying and retrieving those objects between devices and archives.

Every DICOM object belongs to a hierarchy:

```
Patient
 └─ Study          (one exam visit, e.g. "Venous duplex, 16 Oct 2026")
     └─ Series     (one group within the exam, e.g. the images, or the report)
         └─ Instance  (one object: an image, or an SR document)
```

Each level has a globally unique identifier (UID), for example `StudyInstanceUID`, `SeriesInstanceUID` and `SOPInstanceUID`. Each object also has a **SOP Class** that says what kind of object it is (ultrasound image, CT image, Comprehensive SR, ...).

DICOM is maintained by NEMA and is freely available at <https://www.dicomstandard.org/>.

---

## Background: what is a DICOM Structured Report?

A **Structured Report (SR)** is a DICOM object whose payload is not pixels but a **tree of coded statements**. Its *Modality* attribute is `SR`. It is how DICOM stores measurements, findings and observations so that software can read them reliably.

### The content tree

The SR body lives in the `ContentSequence` attribute. It is a tree of **content items**. Every item has:

| Part | Meaning | Example |
|---|---|---|
| **Value type** | What kind of item it is | `NUM`, `CODE`, `CONTAINER` |
| **Concept name** | What the item *is about*, as a code | `Peak Systolic Velocity` (code `11726-7`, scheme `LN`) |
| **Value** | The content | `85.3 cm/s` |
| **Relationship** | How it relates to its parent | `CONTAINS`, `HAS CONCEPT MOD`, `INFERRED FROM` |
| **Children** | Further items nested under it | modifiers, sources, sub-findings |

The value types defined by the standard:

| Value type | Holds | How this tool shows it |
|---|---|---|
| `CONTAINER` | A section/heading grouping other items | Section heading |
| `NUM` | A number with a unit | Row in a measurement table |
| `CODE` | A coded answer (e.g. *Right*, *Patient*, *Mean*) | Key/value row |
| `TEXT` | Free text | Key/value row |
| `PNAME` | A person's name | Key/value row |
| `DATE`, `TIME`, `DATETIME` | Dates and times | Key/value row, formatted |
| `UIDREF` | A reference to a DICOM UID | Key/value row |
| `IMAGE` | A reference to an image in the study | Listed under *Referenced* |
| `COMPOSITE` | A reference to another DICOM object | Listed under *Referenced* |
| `WAVEFORM` | A reference to a waveform (e.g. ECG) | Listed under *Referenced* |
| `SCOORD` / `SCOORD3D` | A point, line, polygon or region drawn on an image | Key/value row (shape and point count; coordinates with `--details`) |
| `TCOORD` | A point or range in time | Key/value row |
| *(by reference)* | An item that points to another item in the tree instead of repeating it | "see content item 1.1.2" |

### Codes and coding schemes

Concept names and coded values are triples of (**code value**, **coding scheme**, **meaning**):

```
(11726-7,       LN,   "Peak Systolic Velocity")   LN   = LOINC
(G-A100,        SRT,  "Right")                    SRT  = SNOMED
(121401,        DCM,  "Derivation")               DCM  = DICOM's own codes
(M-99999-00381, MRUS, "RT VV PROX Distance")      MRUS = a vendor's private scheme (Mindray)
```

Codes let software know that two machines mean the same thing even if their screen labels differ. Humans usually only need the meaning, so this tool hides the codes unless you pass `--details`.

### Templates

The tree's shape follows a **template** (TID) for the kind of exam, for example TID 5100 *Vascular Ultrasound Procedure Report*, TID 5200 *Echocardiography*, TID 5000 *OB-GYN Ultrasound* and TID 1500 *Measurement Report*. A template says which sections and measurements to expect. Vendors fill them in their own way, often with private codes.

### A small example

```
CONTAINER  Vascular Ultrasound Procedure Report
├── CODE       Observer Type = Person
├── PNAME      Subject Name = Doe^Jane
├── CONTAINER  Findings
│   ├── CODE       Finding Site = Carotid Artery
│   └── NUM        Peak Systolic Velocity = 85.3 cm/s
│       └── CODE   (HAS CONCEPT MOD) Laterality = Right
└── IMAGE      Source -> 1.2.840...1234
```

This tool renders that as a header, a *Findings* section, a context row "Finding Site: Carotid Artery", and a measurement table row "Peak Systolic Velocity | 85.3 | cm/s | Laterality: Right".

---

## What the tool does

1. **Reads** an SR file (or every file in a folder) with [pydicom](https://pydicom.github.io/).
2. **Skips** anything that isn't an SR (images, DICOMDIR, other files), so you can point it at a whole exam export.
3. **Builds a report**: a title from the SR's root concept, a header panel from the patient/study/device attributes, then the content tree. Sections become headings, measurements become tables, and everything else becomes labelled rows.
4. **Cleans up for reading**: hides codes and UIDs, trims trailing zeros (`1267.500000` → `1267.5`, never rounds), shows dates as `16 Oct 2026`, shows names as *Given Family*, and shows a reading once when the device stored it twice with the same value.
5. **Checks completeness**: compares every name and value in the SR against the rendered output and warns about anything missing.
6. **Renders** an A4 PDF with repeating table headers and a "Page x of y" footer.

## Who it is for

- **Clinics and sonographers** who need a printable or emailable report of the measurements taken on the machine.
- **Referring physicians and patients** who don't have a DICOM viewer.
- **Researchers and data teams** who want a human-checkable rendering of SR data next to their extracted datasets.
- **Developers and integrators** who need to see exactly what a device puts in its SRs (`--details` shows every code, UID and attribute).
- **QA and audit** work that needs an archived, readable copy of what was measured.

---

## The web app

**<https://haani76.github.io/dicom-sr-to-pdf/>** works in any modern browser (Chrome, Edge, Firefox, Safari) on Windows, macOS, Linux, Android or iOS.

1. Open the page. The converter loads in the background: about 10 seconds the first time, near-instant afterwards because the browser caches it.
2. Click **Choose files** or **Choose a folder**, or drag files or folders onto the page. Files without a `.dcm` extension are fine, and non-SR files are skipped.
3. Optionally tick **Technical details** (the same as `--details` on the command line).
4. Each file is converted in a few seconds. For each result you can:
   - **View**: preview it on the page, or open it in a new browser tab;
   - **Download** the PDF;
   - **Download all (.zip)**: every converted PDF in one zip;
   - **Remove** (on a file or in the preview) or **Remove all**: clears the file, its PDF and the preview from the page.

Each file shows its status: converted (with page count), converted with a warning naming anything not shown, skipped (not an SR), or failed.

**How it works and why it's private.** The page runs the same Python converter as the command-line tool, compiled for the browser with [Pyodide](https://pyodide.org). Your SR files are read and converted on your device. They are never uploaded, and the site has no server that could receive them. The page and the converter program are downloaded **from this site only**, and the browser is instructed (Content-Security-Policy) to block any connection to anywhere else. See [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md).

Note: some mobile browsers can't show PDFs inside a page. Use **Open in new tab** or **Download** there.

## Installation

Requires **Python 3.9+**. Works on Windows, macOS and Linux.

```bash
pip install git+https://github.com/Haani76/dicom-sr-to-pdf
```

Or from a local clone:

```bash
git clone https://github.com/Haani76/dicom-sr-to-pdf
cd dicom-sr-to-pdf
pip install .
```

This installs two dependencies, `pydicom` (reads DICOM) and `xhtml2pdf` (writes PDF), and adds the `dicom-sr-to-pdf` command. No separate PDF program needs to be installed.

---

## Usage

```
dicom-sr-to-pdf INPUT [INPUT ...] [-o OUTPUT] [--details] [--html] [--version]
```

| Option | Meaning |
|---|---|
| `INPUT` | One or more SR files and/or folders. Folders are searched recursively. |
| `-o, --output` | A `.pdf` path (only with a single input file), or a folder for the PDFs. Default: each PDF next to its input file. |
| `--details` | Full technical view: codes, every raw reading, image UIDs, coordinates, and an appendix of all DICOM attributes. |
| `--html` | Also keep the intermediate HTML next to the PDF. Handy for checking content or restyling. |
| `--version` | Print the version. |

### Examples

```bash
# One file; PDF lands next to it as report.pdf
dicom-sr-to-pdf report.dcm

# Choose the output file
dicom-sr-to-pdf report.dcm -o out/patient-123.pdf

# Whole exam export, all SRs found anywhere under exams/, PDFs into pdfs/
dicom-sr-to-pdf exams/ -o pdfs/

# Several inputs at once
dicom-sr-to-pdf a.dcm b.dcm more_reports/

# Full technical view, e.g. to compare with a DICOM viewer line by line
dicom-sr-to-pdf report.dcm --details -o report_details.pdf

# Without installing the command
python -m dicom_sr_to_pdf report.dcm
```

Typical output:

```
ok    exams\1.2.156...130.dcm -> pdfs\1.2.156...130.pdf
skip  exams\DICOMDIR: not a DICOM Structured Report
skip  exams\IMG0001: not a DICOM Structured Report
1 converted, 2 skipped, 0 failed
```

---

## What the PDF contains

1. **Title**: the SR's root concept, e.g. *Vascular Ultrasound Procedure Report*, and the report's content date and time.
2. **Header panel** with whichever of these the file contains (empty ones are left out): patient name, patient ID, sex / date of birth, accession number, study description, study ID, protocol, study date and time, institution, department, referring physician, performing physician, operator, device (manufacturer and model), serial number, software version, and completion / verification status.
3. **Observation context**: who made the observations, their organization and role, subject details.
4. **Sections**: one heading per `CONTAINER`, with nested sub-headings for nested sections.
5. **Measurement tables** with the columns *Measurement · Value · Unit · Qualifiers*. Qualifiers include concept modifiers (laterality, derivation such as *Mean*, selection status) and anything else nested under the measurement. Table headers repeat on every page.
6. **Other items** as labelled rows, with their nested items listed beneath.
7. **Referenced images and objects**, summarised per section (e.g. *Referenced: Image ×11*).
8. **Footer** on every page: generation time, tool version, a "not a signed clinical report" note, and *Page x of y*.

## Default view vs `--details`

| | Default | `--details` |
|---|---|---|
| Measurement names and values | ✔ | ✔ |
| Units, qualifiers, context, nested items | ✔ | ✔ |
| Repeated identical readings | shown once | every copy shown |
| Coding-scheme codes, e.g. `(121401, DCM)` | hidden | ✔ |
| Referenced image/object UIDs, frame numbers | count only | ✔ |
| Spatial coordinates (`SCOORD`) | shape and point count | ✔ every point |
| Appendix: every DICOM attribute outside the report tree | – | ✔ |

**About repeated readings.** Some devices store each measurement twice: Mindray, for example, stores the raw reading and then a copy marked *Derivation: Mean, Selection Status: Mean value chosen*. The default view keeps only the later copy, **and only when both name and value are identical**. Readings with different values are always all shown.

## Completeness check and warnings

After building each report, the tool walks the whole SR content tree and confirms that every concept name and every value (codes, numbers, units, text, names, UIDs) appears in the output. If anything doesn't, it prints a warning naming it:

```
WARN  report.dcm: not shown in PDF: unsupported item type XYZ
```

The PDF is still written. The warning tells you exactly what to look for. On a clean conversion there is no `WARN` line.

## Batch conversion

- Folders are searched **recursively**, and files are recognised by content, not by extension. DICOM files often have no extension or are named by UID.
- Non-SR files are **skipped** with a `skip` line.
- A file that fails to convert prints a `FAIL` line and **does not stop the batch**.
- With `-o FOLDER`, every PDF goes into that folder, named after its input file.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | At least one file converted and none failed |
| `1` | A file failed, or nothing was converted (e.g. no SRs found) |
| `2` | Bad command-line arguments |

Useful in scripts and scheduled jobs.

## Using it from Python

```python
from dicom_sr_to_pdf.report import render

html, pdf_bytes, missing = render("report.dcm", details=False)  # path or file-like object
assert missing == []          # nothing dropped
open("report.pdf", "wb").write(pdf_bytes)
```

`render` raises `ValueError` if the file is not an SR. `html` is plain HTML, so you can also show it in a web app or post-process it. For a dataset you've already loaded, use `build_html(ds)` and `missing_values(ds, html)`.

## How it works internally

```
dicom_sr_to_pdf/
├── cli.py       command line: finds inputs, skips non-SR, loops, reports ok/skip/WARN/FAIL
├── report.py    SR -> HTML (header, content tree, tables, styling) and HTML -> PDF
└── __main__.py  enables `python -m dicom_sr_to_pdf`
web/
├── index.html          the web app page, with its Content-Security-Policy
├── app.js              upload, results, preview, downloads
├── worker.js           runs report.py in the browser (Pyodide), off the main thread
├── build_site.py       assembles _site/, downloading and hash-checking every third-party file
└── vendor-lock.json    pinned Pyodide runtime and Python wheels, with SHA-256 fingerprints
tests/
└── test_convert.py   builds synthetic SRs (fake patients) and checks the output
```

- `render_items` walks one level of the content tree. It groups consecutive `NUM` items into a table, turns `CONTAINER`s into headings and recurses into them, and turns everything else into labelled rows.
- `value_text` knows how to display every SR value type. `child_lines` flattens anything nested under a non-section item.
- `missing_values` is the completeness check, used by the CLI and the tests.
- PDF rendering uses `xhtml2pdf`, which is pure Python, so there's nothing else to install.

## Privacy and patient data

SR files and the PDFs made from them contain **protected health information**: patient names, IDs, dates and institution.

- Everything runs **locally**. The command-line tool makes no network connections, and the web app converts inside your browser without uploading your files. The browser itself blocks the web app from contacting any other server.
- For HIPAA/GDPR reviews, see **[SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)**: data flow, technical safeguards, and what remains your organization's responsibility.
- Don't commit `.dcm`, `.pdf` or `.html` files to version control. The included `.gitignore` excludes them.
- Before sharing outputs for testing or support, use anonymised SRs. The test suite generates its own fake data for this reason.
- The PDF is a **readable rendering** of the SR, **not a signed clinical report**, and it says so in every footer. Clinical sign-off belongs in your reporting system.

## Limitations

- **Readability, not interpretation.** The tool prints what the SR contains. It doesn't calculate, interpret, or apply clinical criteria.
- **Labels come from the device.** Names such as `RT GSV PROX SIZE Distance*` (asterisk included) are printed exactly as the machine wrote them.
- **Numbers are not rounded.** Trailing zeros are trimmed, but `0.439205 cm` stays `0.439205 cm`.
- **Images are referenced, not embedded.** The SR only points to images by UID, so the PDF lists the references but doesn't include pictures.
- **Encapsulated PDF/CDA reports** (DICOM objects that wrap an existing PDF or document) are not Structured Reports and are skipped.
- **Tested on** Mindray vascular ultrasound SRs (TID 5100) and synthetic SRs covering every value type. Other vendors and templates should work, and the completeness warning tells you if one doesn't.

## Troubleshooting / FAQ

**`skip ... not a DICOM Structured Report`**
That file isn't an SR: it's an image, a DICOMDIR, or not DICOM at all. That's expected when converting a whole exam folder.

**Nothing converted, exit code 1**
No SR files were found. Check the path. SRs are often in their own series folder inside an export.

**A `WARN ... not shown in PDF` line**
The SR contains something the PDF didn't show. The warning names it. Please open an issue with an **anonymised** example.

**The values look different from my viewer.**
Run with `--details`. It shows every raw reading and code, matching what viewers like MicroDicom list. In the default view, identical repeated readings are merged and trailing zeros trimmed.

**The patient name order differs from my viewer's tag panel.**
DICOM stores names as `Family^Given`. The PDF prints them as *Given Family*, as report-style viewers do. The raw value is in the `--details` appendix.

**Sex shows "Other" in the header but "Unknown sex" in the body.**
Those come from two different places in the file (the `PatientSex` attribute and an SR observation), and the device filled them differently. The tool prints both as stored.

**Can I change the look (colors, logo, fonts)?**
Yes. The styling is the `CSS` block in `report.py`. Use `--html` to iterate quickly in a browser.

## Development

```bash
git clone https://github.com/Haani76/dicom-sr-to-pdf
cd dicom-sr-to-pdf
pip install -e ".[test]"
pytest
```

Tests build synthetic SRs with fake patients. These cover common content plus rare cases (coordinates, time points, by-reference items, nested findings, non-numeric measurements, and an unknown value type), so no real data is needed.

## Versions and rolling back

Every release is tagged: `v1.0.0`, `v1.1.0`, ... (see the repository's *Tags*). Each tag is a complete snapshot of the tool: website, converter and docs.

**Switch the live website to any version, older or newer:**

1. Open the repository's **Actions** tab → **Deploy web app** → **Run workflow**.
2. Enter the version, e.g. `v1.0.0`, and click **Run workflow**.
3. About 2 minutes later the site serves exactly that version. The footer shows the converter version.

To return to the latest version, run the workflow with the field left empty. Note that **any push to `main` also publishes the latest version**, so after a rollback, avoid pushing to `main` until you're ready to move forward.

**Command-line tool at a specific version:**

```bash
pip install --force-reinstall "git+https://github.com/Haani76/dicom-sr-to-pdf@v1.0.0"
```

**Making a new release:** bump `__version__` in `dicom_sr_to_pdf/__init__.py`, commit, then tag and push:

```bash
git tag -a v1.2.0 -m "v1.2.0: what changed"
git push origin v1.2.0
```

## Hosting your own copy of the web app

The web app is a static site, so any static host works, free. `web/build_site.py` assembles it into `_site/`: the page, the converter, and the Python runtime and packages, which it downloads and checks against the SHA-256 fingerprints in `web/vendor-lock.json`. It refuses to build if anything doesn't match. It needs only Python 3.9+.

```bash
python web/build_site.py
```

**GitHub Pages (used by this repo).** `.github/workflows/pages.yml` runs the tests, builds and publishes on every push to `main`, and can publish any tagged version on demand (see above). One-time setup in a fork: *Settings → Pages → Build and deployment → Source: **GitHub Actions***. The site appears at `https://<user>.github.io/<repo>/`.

**Cloudflare Pages / Netlify / an internal web server.** Build command `python web/build_site.py`, output directory `_site`. For a fully offline intranet copy, build once on a machine with internet access and copy `_site/` to the internal server.

**Locally**, for development: `python web/build_site.py`, then `python -m http.server -d _site` and open <http://localhost:8000>. Opening `index.html` straight from disk won't work.

**Upgrading the runtime or packages:** edit the pins at the top of `web/build_site.py`, run `python web/build_site.py --lock` to re-resolve them and record new fingerprints, test, then commit `web/vendor-lock.json`.

## Glossary

| Term | Meaning |
|---|---|
| **DICOM** | Digital Imaging and Communications in Medicine, the standard for medical images and related data |
| **SR** | Structured Report, a DICOM object holding coded measurements and findings as a tree |
| **Attribute / tag** | One field in a DICOM file, e.g. `(0010,0010) PatientName` |
| **VR** | Value Representation, the data type of an attribute |
| **Content item** | One node of the SR tree |
| **Value type** | The kind of content item: `NUM`, `CODE`, `CONTAINER`, ... |
| **Concept name** | The coded "question" a content item answers |
| **Coding scheme** | The vocabulary a code comes from: LOINC (`LN`), SNOMED (`SRT`/`SCT`), DICOM (`DCM`), or vendor-private |
| **TID** | Template ID, the expected structure for a kind of report |
| **UCUM** | Unified Code for Units of Measure, the standard for units like `cm/s` |
| **UID** | A globally unique identifier for a study, series, object or class |
| **SOP Class** | The type of a DICOM object (e.g. *Comprehensive SR*) |
| **PACS** | Picture Archiving and Communication System, a hospital image archive |
| **Modality** | The kind of device or data: `US`, `CT`, `MR`, `SR`, ... |
