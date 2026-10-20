"""Turn a DICOM Structured Report dataset into report HTML and PDF."""
import io
from datetime import datetime
from html import escape

import pydicom
from xhtml2pdf import pisa

from . import __version__

SEX = {"M": "Male", "F": "Female", "O": "Other"}


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


KNOWN_TYPES = ("CONTAINER", "NUM", "CODE", "TEXT", "PNAME", "DATE", "TIME", "DATETIME", "UIDREF",
               "IMAGE", "COMPOSITE", "WAVEFORM", "SCOORD", "SCOORD3D", "TCOORD")
REF_TYPES = ("IMAGE", "COMPOSITE", "WAVEFORM")


def fmt_num(v):
    s = str(v if v is not None else "")
    return s.rstrip("0").rstrip(".") if "." in s and "e" not in s.lower() else s


def fmt_list(v):
    if isinstance(v, str) or not hasattr(v, "__iter__"):
        return fmt_num(v)
    return ", ".join(fmt_num(x) for x in v)


def num_parts(item):
    """(value, unit) of a NUM item; value falls back to the qualifier (e.g. 'Not a number')."""
    if getattr(item, "MeasuredValueSequence", None):
        mv = item.MeasuredValueSequence[0]
        # UCUM code: cm, cm/s, ms
        return fmt_num(getattr(mv, "NumericValue", "")), code(mv, "MeasurementUnitsCodeSequence")[1]
    return code(item, "NumericValueQualifierCodeSequence")[0], ""


def ref_text(item, details):
    label = {"IMAGE": "Image", "COMPOSITE": "Referenced object", "WAVEFORM": "Waveform"}[item.ValueType]
    if not details:
        return label
    parts = []
    for ref in getattr(item, "ReferencedSOPSequence", []):
        parts.append(f"<span class='code'>{esc(getattr(ref, 'ReferencedSOPInstanceUID', ''))}</span>")
        for attr, name in (("ReferencedFrameNumber", "frames"), ("ReferencedSegmentNumber", "segments"),
                           ("ReferencedWaveformChannels", "channels")):
            if attr in ref:
                parts.append(f"{name} {esc(fmt_list(ref[attr].value))}")
    return f"{label}: " + " ".join(parts)


def value_text(item, details):
    """Readable value of any SR content item, as HTML."""
    vt = getattr(item, "ValueType", "")
    if not vt and "ReferencedContentItemIdentifier" in item:
        target = ".".join(str(x) for x in item.ReferencedContentItemIdentifier)
        return f"see content item {esc(target)}"
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
    if vt == "UIDREF":
        return esc(getattr(item, "UID", ""))
    if vt == "NUM":
        return esc(" ".join(x for x in num_parts(item) if x))
    if vt in REF_TYPES:
        return ref_text(item, details)
    if vt in ("SCOORD", "SCOORD3D"):
        pts = list(getattr(item, "GraphicData", []))
        n = len(pts) // (3 if vt == "SCOORD3D" else 2)
        text = f"{esc(getattr(item, 'GraphicType', ''))} ({n} point{'' if n == 1 else 's'})"
        if details:
            text += f" <span class='code'>[{esc(fmt_list(pts))}]</span>"
        return text
    if vt == "TCOORD":
        text = esc(getattr(item, "TemporalRangeType", ""))
        for attr in ("ReferencedSamplePositions", "ReferencedTimeOffsets", "ReferencedDateTime"):
            if attr in item:
                text += f" <span class='code'>{esc(fmt_list(item[attr].value))}</span>"
        return text
    if vt == "CONTAINER":
        return ""
    return f"[unsupported value type {esc(vt)}]"


def child_lines(item, details, indent=0):
    """Every nested item below a non-container item, flattened to 'Name: value' lines."""
    lines = []
    for child in getattr(item, "ContentSequence", []):
        name = with_code(*code(child, "ConceptNameCodeSequence"), details)
        value = value_text(child, details)
        pad = "&nbsp;&nbsp;" * indent
        lines.append(f"{pad}{name}: {value}" if value and name else f"{pad}{name or value}")
        lines.extend(child_lines(child, details, indent + 1))
    return lines


def num_key(item):
    """(concept name, value) used to spot a raw reading repeated as its 'mean chosen' copy."""
    return code(item, "ConceptNameCodeSequence")[0], num_parts(item)[0]


def measurement_row(item, details):
    name = with_code(*code(item, "ConceptNameCodeSequence"), details)
    value, unit = num_parts(item)
    return (f"<tr><td class='name'>{name}</td><td class='num'>{esc(value)}</td>"
            f"<td>{esc(unit)}</td><td class='mods'>{'<br/>'.join(child_lines(item, details))}</td></tr>")


def render_items(seq, depth, details):
    """Render one ContentSequence level, grouping runs of measurements into tables."""
    out, rows, context, refs = [], [], [], []
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
        name = with_code(*code(item, "ConceptNameCodeSequence"), details)
        if vt == "NUM":
            key = num_key(item)
            if not details and keys and keys[-1] == key:
                rows.pop()  # same reading again (e.g. Mindray "mean value chosen"): keep the later one
                keys.pop()
            rows.append(measurement_row(item, details))
            keys.append(key)
        elif vt == "CONTAINER":
            flush()
            level = min(depth + 2, 4)
            out.append(f"<h{level}>{name}</h{level}>")
            out.extend(render_items(getattr(item, "ContentSequence", []), depth + 1, details))
            after_section = True
        elif vt in REF_TYPES and "ContentSequence" not in item:
            refs.append((name, ref_text(item, details)))
        else:
            sub = child_lines(item, details)
            extra = "<br/><span class='mods'>" + "<br/>".join(sub) + "</span>" if sub else ""
            context.append(f"<tr><td class='k'>{name}</td><td>{value_text(item, details)}{extra}</td></tr>")
    flush()
    if refs:
        if details:
            note = "Referenced images/objects:<br/>" + "<br/>".join(f"{n}: {t}" if n else t for n, t in refs)
        else:
            counts = {}
            for n, t in refs:
                counts[(n, t)] = counts.get((n, t), 0) + 1
            note = "Referenced: " + "; ".join(
                (f"{n} ({t}" if n else t) + (f" &times;{c}" if c > 1 else "") + (")" if n else "")
                for (n, t), c in counts.items())
        out.append(f"<p class='images'>{note}</p>")
    return out


def missing_values(ds, html, details=False):
    """Names and values from the SR that do not appear in the rendered HTML (should be empty)."""
    want = []

    def walk(seq):
        for it in seq:
            vt = getattr(it, "ValueType", "")
            want.append(code(it, "ConceptNameCodeSequence")[0])
            if vt and vt not in KNOWN_TYPES:
                want.append(f"unsupported item type {vt}")  # never in the HTML, so always reported
            if vt == "CODE":
                want.append(code(it, "ConceptCodeSequence")[0])
            elif vt == "NUM":
                want.extend(num_parts(it))
            elif vt == "TEXT":
                want.append(getattr(it, "TextValue", ""))
            elif vt == "PNAME":
                want.append(fmt_name(getattr(it, "PersonName", "")))
            elif vt == "UIDREF":
                want.append(getattr(it, "UID", ""))
            elif details and vt in REF_TYPES:
                want.extend(getattr(r, "ReferencedSOPInstanceUID", "") for r in getattr(it, "ReferencedSOPSequence", []))
            walk(getattr(it, "ContentSequence", []))

    walk(getattr(ds, "ContentSequence", []))
    return sorted({w for w in map(str, want) if w and escape(w) not in html})


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
.attrs td { padding: 1pt 3pt; font-size: 7.5pt; vertical-align: top; }
.attrs .k { width: 55%; color: #52606d; }
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
        ("Study ID", getattr(ds, "StudyID", "")),
        ("Protocol", getattr(ds, "ProtocolName", "")),
        ("Study date", f"{fmt_date(getattr(ds, 'StudyDate', ''))} {fmt_time(getattr(ds, 'StudyTime', ''))}".strip()),
        ("Institution", getattr(ds, "InstitutionName", "")),
        ("Department", getattr(ds, "InstitutionalDepartmentName", "")),
        ("Referring", fmt_name(getattr(ds, "ReferringPhysicianName", ""))),
        ("Performing", fmt_name(getattr(ds, "PerformingPhysicianName", ""))),
        ("Operator", fmt_name(getattr(ds, "OperatorsName", ""))),
        ("Device", " ".join(str(x) for x in (getattr(ds, "Manufacturer", ""),
                                             getattr(ds, "ManufacturerModelName", "")) if x)),
        ("Serial no.", getattr(ds, "DeviceSerialNumber", "")),
        ("Software", getattr(ds, "SoftwareVersions", "")),
        ("Status", " / ".join(str(x).title() for x in (getattr(ds, "CompletionFlag", ""),
                                                      getattr(ds, "VerificationFlag", "")) if x)),
    ]
    fields = [(k, v) for k, v in fields if str(v).strip()]
    cells = [f"<td class='k'>{esc(k)}</td><td>{esc(v)}</td>" for k, v in fields]
    header_rows = "".join("<tr>" + "".join(cells[i:i + 2]) + "</tr>" for i in range(0, len(cells), 2))
    content_dt = f"{fmt_date(getattr(ds, 'ContentDate', ''))} {fmt_time(getattr(ds, 'ContentTime', ''))}".strip()
    body = "\n".join(render_items(getattr(ds, "ContentSequence", []), 0, details))
    if details:
        body += ("<h2>All DICOM attributes</h2><table class='attrs'>"
                 + "".join(f"<tr><td class='k'>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in attributes(ds))
                 + "</table>")
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


def attributes(ds, prefix=""):
    """(name, value) for every non-empty attribute outside the SR content tree, sequences flattened."""
    out = []
    for el in ds:
        if el.keyword in ("ContentSequence", "PixelData") or el.value in (None, "", b""):
            continue
        name = prefix + (el.keyword or f"Private {el.tag}")
        if el.VR == "SQ":
            for i, sub in enumerate(el.value, 1):
                out += attributes(sub, f"{name}[{i}].")
        elif isinstance(el.value, bytes):
            out.append((name, f"<{len(el.value)} bytes>"))
        else:
            out.append((name, el.value))
    return out


def render(src, details=False):
    """Read an SR (path or file-like) and return (html, pdf bytes, values missing from the PDF)."""
    ds = pydicom.dcmread(src)
    if getattr(ds, "Modality", "") != "SR" or "ContentSequence" not in ds:
        raise ValueError("not a DICOM Structured Report")
    html = build_html(ds, details=details)
    buf = io.BytesIO()
    if pisa.CreatePDF(html, dest=buf, encoding="utf-8").err:
        raise RuntimeError("PDF rendering failed")
    return html, buf.getvalue(), missing_values(ds, html, details)
