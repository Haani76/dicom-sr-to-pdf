"""Turn a DICOM Structured Report dataset into report HTML and PDF."""
from datetime import datetime
from html import escape

from xhtml2pdf import pisa

from . import __version__

SEX = {"M": "Male", "F": "Female", "O": "Other"}
CONTEXT_TYPES = ("CODE", "TEXT", "PNAME", "DATE", "TIME", "DATETIME", "UIDREF")


def esc(value):
    return escape(str(value if value is not None else ""))


def fmt_date(d):
    d = str(d or "")
    try:
        return datetime.strptime(d[:8], "%Y%m%d").strftime("%d %b %Y")
    except ValueError:
        return d


def fmt_time(t):
    t = str(t or "").split(".")[0]
    return f"{t[0:2]}:{t[2:4]}:{t[4:6]}" if len(t) >= 6 else t


def fmt_name(pn):
    # DICOM PN is Family^Given^Middle^Prefix^Suffix
    parts = [p for p in str(pn or "").split("^") if p]
    return " ".join(parts[1:] + parts[:1]) if parts else ""


def code(item, attr):
    """(meaning, value, scheme) of the first entry of a code sequence, or blanks."""
    seq = getattr(item, attr, None)
    if not seq:
        return "", "", ""
    c = seq[0]
    return (getattr(c, "CodeMeaning", ""), getattr(c, "CodeValue", ""),
            getattr(c, "CodingSchemeDesignator", ""))


def with_code(meaning, value, scheme, details):
    return f"{esc(meaning)} <span class='code'>({esc(value)}, {esc(scheme)})</span>" \
        if details and value else esc(meaning)


def context_value(item, details):
    vt = item.ValueType
    if vt == "CODE":
        return with_code(*code(item, "ConceptCodeSequence"), details)
    if vt == "TEXT":
        return esc(getattr(item, "TextValue", ""))
    if vt == "PNAME":
        return esc(fmt_name(getattr(item, "PersonName", "")))
    if vt == "DATE":
        return esc(fmt_date(getattr(item, "Date", "")))
    if vt == "TIME":
        return esc(fmt_time(getattr(item, "Time", "")))
    if vt == "DATETIME":
        dt = str(getattr(item, "DateTime", ""))
        return esc(f"{fmt_date(dt[:8])} {fmt_time(dt[8:])}".strip())
    return esc(getattr(item, "UID", ""))


def fmt_num(v):
    s = str(v if v is not None else "")
    return s.rstrip("0").rstrip(".") if "." in s and "e" not in s.lower() else s


def num_key(item):
    """(concept name, value) used to spot a raw reading repeated as its 'mean chosen' copy."""
    mv = item.MeasuredValueSequence[0] if getattr(item, "MeasuredValueSequence", None) else None
    return code(item, "ConceptNameCodeSequence")[0], fmt_num(getattr(mv, "NumericValue", ""))


def measurement_row(item, details):
    name = with_code(*code(item, "ConceptNameCodeSequence"), details)
    value = unit = ""
    if getattr(item, "MeasuredValueSequence", None):
        mv = item.MeasuredValueSequence[0]
        value = fmt_num(getattr(mv, "NumericValue", ""))
        unit = code(mv, "MeasurementUnitsCodeSequence")[1]  # UCUM code: cm, cm/s, ms
    mods = []
    for child in getattr(item, "ContentSequence", []):
        if getattr(child, "RelationshipType", "") in ("HAS CONCEPT MOD", "HAS PROPERTIES"):
            mods.append(f"{esc(code(child, 'ConceptNameCodeSequence')[0])}: "
                        f"{with_code(*code(child, 'ConceptCodeSequence'), details)}")
    return (f"<tr><td class='name'>{name}</td><td class='num'>{esc(value)}</td>"
            f"<td>{esc(unit)}</td><td class='mods'>{'<br/>'.join(mods)}</td></tr>")


def render_items(seq, depth, details):
    """Render one ContentSequence level, grouping runs of measurements into tables."""
    out, rows, context, images = [], [], [], []
    keys = []  # num_key per row, parallel to rows
    after_section = False

    def flush():
        if rows and after_section:
            # without this, trailing measurements read as part of the section above
            out.append(f"<h{min(depth + 2, 4)}>Measurements</h{min(depth + 2, 4)}>")
        if context:
            out.append("<table class='context'>" + "".join(context) + "</table>")
            context.clear()
        if rows:
            out.append("<table class='meas' repeat='1'><thead><tr><th>Measurement</th>"
                       "<th class='num'>Value</th><th>Unit</th><th>Qualifiers</th></tr></thead>"
                       + "".join(rows) + "</table>")
            rows.clear()
            keys.clear()

    for item in seq:
        vt = getattr(item, "ValueType", "")
        if vt == "NUM":
            key = num_key(item)
            if not details and keys and keys[-1] == key:
                rows.pop()  # same reading again (e.g. Mindray "mean value chosen"): keep the later one
                keys.pop()
            rows.append(measurement_row(item, details))
            keys.append(key)
        elif vt in CONTEXT_TYPES:
            name = with_code(*code(item, "ConceptNameCodeSequence"), details)
            context.append(f"<tr><td class='k'>{name}</td><td>{context_value(item, details)}</td></tr>")
        elif vt == "IMAGE":
            ref = item.ReferencedSOPSequence[0] if getattr(item, "ReferencedSOPSequence", None) else None
            images.append(getattr(ref, "ReferencedSOPInstanceUID", ""))
        elif vt == "CONTAINER":
            flush()
            level = min(depth + 2, 4)
            out.append(f"<h{level}>{esc(code(item, 'ConceptNameCodeSequence')[0])}</h{level}>")
            out.extend(render_items(getattr(item, "ContentSequence", []), depth + 1, details))
            after_section = True
    flush()
    if images:
        note = f"{len(images)} referenced image{'s' if len(images) > 1 else ''}"
        if details:
            note += ":<br/>" + "<br/>".join(f"<span class='code'>{esc(u)}</span>" for u in images)
        out.append(f"<p class='images'>{note}</p>")
    return out


CSS = """
@page { size: a4 portrait; margin: 16mm 14mm 18mm 14mm;
  @frame footer { -pdf-frame-content: footer; bottom: 8mm; margin-left: 14mm; margin-right: 14mm; height: 8mm; } }
body { font-family: Helvetica; font-size: 9.5pt; color: #1f2933; }
h1 { font-size: 16pt; color: #0b4f6c; margin: 0 0 2pt 0; }
.subtitle { color: #52606d; font-size: 9pt; margin-bottom: 8pt; }
h2 { font-size: 11.5pt; color: #ffffff; background-color: #0b4f6c; padding: 4pt 6pt 2pt 6pt; margin: 12pt 0 4pt 0; }
h3 { font-size: 10.5pt; color: #0b4f6c; border-bottom: 1px solid #9fb3c8; padding-bottom: 1pt; margin: 9pt 0 3pt 0; }
h4 { font-size: 9.5pt; color: #334e68; margin: 6pt 0 2pt 0; }
table { width: 100%; }
.header { border-top: 2px solid #0b4f6c; border-bottom: 1px solid #9fb3c8; background-color: #f0f4f8; }
.header td { padding: 3pt 4pt 1pt 4pt; vertical-align: top; border: none; }
.k { color: #52606d; width: 22%; }
.context td { padding: 1pt 3pt; font-size: 8.5pt; }
.meas { margin-top: 3pt; }
.meas th { background-color: #d9e2ec; color: #102a43; text-align: left; padding: 3pt 4pt 1pt 4pt; font-size: 8.5pt; }
.meas td { padding: 3pt 4pt 1pt 4pt; border-bottom: 0.5px solid #d9e2ec; vertical-align: top; }
.meas .name { width: 38%; font-weight: bold; }
.num { text-align: right; width: 12%; }
.mods { color: #52606d; font-size: 8pt; width: 38%; }
.code { color: #829ab1; font-size: 7pt; font-weight: normal; }
.images { color: #52606d; font-size: 8pt; font-style: italic; margin-top: 3pt; }
#footer { color: #829ab1; font-size: 7.5pt; border-top: 0.5px solid #bcccdc; padding-top: 2pt; }
"""


def build_html(ds, details=False):
    title = code(ds, "ConceptNameCodeSequence")[0] or "Structured Report"
    sex = SEX.get(str(getattr(ds, "PatientSex", "")), "")
    dob = fmt_date(getattr(ds, "PatientBirthDate", ""))
    fields = [
        ("Patient", fmt_name(getattr(ds, "PatientName", ""))),
        ("Patient ID", getattr(ds, "PatientID", "")),
        ("Sex / DOB", " / ".join(x for x in (sex, dob) if x)),
        ("Accession", getattr(ds, "AccessionNumber", "")),
        ("Study", getattr(ds, "StudyDescription", "")),
        ("Study date", f"{fmt_date(getattr(ds, 'StudyDate', ''))} {fmt_time(getattr(ds, 'StudyTime', ''))}".strip()),
        ("Institution", getattr(ds, "InstitutionName", "")),
        ("Referring", fmt_name(getattr(ds, "ReferringPhysicianName", ""))),
        ("Device", " ".join(str(x) for x in (getattr(ds, "Manufacturer", ""),
                                             getattr(ds, "ManufacturerModelName", "")) if x)),
        ("Status", " / ".join(str(x).title() for x in (getattr(ds, "CompletionFlag", ""),
                                                      getattr(ds, "VerificationFlag", "")) if x)),
    ]
    fields = [(k, v) for k, v in fields if str(v).strip()]
    cells = [f"<td class='k'>{esc(k)}</td><td>{esc(v)}</td>" for k, v in fields]
    header_rows = "".join("<tr>" + "".join(cells[i:i + 2]) + "</tr>" for i in range(0, len(cells), 2))
    content_dt = f"{fmt_date(getattr(ds, 'ContentDate', ''))} {fmt_time(getattr(ds, 'ContentTime', ''))}".strip()
    body = "\n".join(render_items(getattr(ds, "ContentSequence", []), 0, details))
    generated = datetime.now().strftime("%d %b %Y %H:%M")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>{esc(title)}</title><style>{CSS}</style></head>
<body>
<h1>{esc(title)}</h1>
<div class="subtitle">DICOM Structured Report{' &middot; Content ' + esc(content_dt) if content_dt else ''}</div>
<table class="header">{header_rows}</table>
{body}
<div id="footer">Generated {generated} by dicom-sr-to-pdf {__version__} from the DICOM SR.
Not a signed clinical report. &nbsp;&middot;&nbsp; Page <pdf:pagenumber/> of <pdf:pagecount/></div>
</body></html>"""


def write_pdf(html, pdf_path):
    with open(pdf_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF rendering failed for {pdf_path}")
