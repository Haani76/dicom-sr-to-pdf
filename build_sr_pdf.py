import os
import sys
import pydicom
import subprocess

if len(sys.argv) < 2:
    print("Usage: python build_sr_pdf.py <input_sr.dcm> [output.pdf]")
    sys.exit(1)

dcm_path = sys.argv[1]
pdf_path = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(dcm_path)[0] + ".pdf"
html_path = os.path.splitext(pdf_path)[0] + ".html"

ds = pydicom.dcmread(dcm_path)

def esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def fmt_date(d):
    if not d: return ""
    d = str(d)
    if len(d) == 8:
        return f"{d[6:8]}-{d[4:6]}-{d[0:4]}"
    return d

def fmt_time(t):
    if not t: return ""
    t = str(t).split('.')[0]
    if len(t) >= 6:
        return f"{t[0:2]}:{t[2:4]}:{t[4:6]}"
    return t

def get_code_display(item_cn_seq, item_val_seq):
    """Return (name, value_str) for a CODE item."""
    name = ""
    val_meaning = val_code = val_scheme = ""
    if item_cn_seq:
        c = item_cn_seq[0]
        name = getattr(c, 'CodeMeaning', '')
    if item_val_seq:
        c = item_val_seq[0]
        val_meaning = getattr(c, 'CodeMeaning', '')
        val_code = getattr(c, 'CodeValue', '')
        val_scheme = getattr(c, 'CodingSchemeDesignator', '')
    return name, val_meaning, val_code, val_scheme

def render_content_seq(seq, depth=0):
    """Render a content sequence to HTML blocks."""
    blocks = []
    for item in seq:
        vt = getattr(item, 'ValueType', '')
        rel = getattr(item, 'RelationshipType', '')

        # Get concept name
        cn_meaning = cn_code = cn_scheme = ""
        if hasattr(item, 'ConceptNameCodeSequence') and item.ConceptNameCodeSequence:
            c = item.ConceptNameCodeSequence[0]
            cn_meaning = getattr(c, 'CodeMeaning', '')
            cn_code = getattr(c, 'CodeValue', '')
            cn_scheme = getattr(c, 'CodingSchemeDesignator', '')

        if vt == 'CONTAINER':
            # Cyan section header
            blocks.append(f'<div class="section-header">{esc(cn_meaning)}</div>')
            if hasattr(item, 'ContentSequence'):
                blocks.extend(render_content_seq(item.ContentSequence, depth+1))

        elif vt == 'NUM':
            # Get value and unit
            value_str = ""
            unit_str = ""
            if hasattr(item, 'MeasuredValueSequence') and item.MeasuredValueSequence:
                mv = item.MeasuredValueSequence[0]
                num_val = getattr(mv, 'NumericValue', '')
                value_str = str(num_val)
                if hasattr(mv, 'MeasurementUnitsCodeSequence') and mv.MeasurementUnitsCodeSequence:
                    u = mv.MeasurementUnitsCodeSequence[0]
                    unit_str = getattr(u, 'CodeValue', '')  # Use CodeValue: cm, s, mm, ms

            # Check if it has children (means it's the "mean chosen" variant)
            children = []
            if hasattr(item, 'ContentSequence') and item.ContentSequence:
                for child in item.ContentSequence:
                    child_rel = getattr(child, 'RelationshipType', '')
                    child_vt = getattr(child, 'ValueType', '')
                    child_cn = ""
                    child_val = child_val_code = child_val_scheme = ""
                    if hasattr(child, 'ConceptNameCodeSequence') and child.ConceptNameCodeSequence:
                        child_cn = getattr(child.ConceptNameCodeSequence[0], 'CodeMeaning', '')
                    if hasattr(child, 'ConceptCodeSequence') and child.ConceptCodeSequence:
                        c = child.ConceptCodeSequence[0]
                        child_val = getattr(c, 'CodeMeaning', '')
                        child_val_code = getattr(c, 'CodeValue', '')
                        child_val_scheme = getattr(c, 'CodingSchemeDesignator', '')
                    children.append((child_rel, child_cn, child_val, child_val_code, child_val_scheme))

            # Name display: concept name + asterisk if it ends with *
            display_name = esc(cn_meaning) + '*'

            block = f'<div class="meas-block">'
            block += f'<div class="meas-name">{display_name}:</div>'
            block += f'<div class="meas-value">{esc(value_str)} {esc(unit_str)}</div>'

            for (c_rel, c_cn, c_val, c_val_code, c_val_scheme) in children:
                if c_rel == 'HAS CONCEPT MOD':
                    block += f'<div class="meas-mod">Concept Modifier: {esc(c_cn)} = {esc(c_val)} ({esc(c_val_code)}, {esc(c_val_scheme)})</div>'
                elif c_rel == 'HAS PROPERTIES':
                    block += f'<div class="meas-mod">Properties: {esc(c_cn)} = {esc(c_val)} ({esc(c_val_code)}, {esc(c_val_scheme)})</div>'

            block += '</div>'
            blocks.append(block)

        elif vt == 'IMAGE':
            # Image reference
            ref_uid = ""
            if hasattr(item, 'ReferencedSOPSequence') and item.ReferencedSOPSequence:
                ref_uid = getattr(item.ReferencedSOPSequence[0], 'ReferencedSOPInstanceUID', '')
            blocks.append(f'<div class="img-ref">Go Image <span class="uid-small">[{esc(ref_uid)}]</span></div>')

        elif vt in ('CODE', 'TEXT', 'PNAME', 'DATETIME', 'DATE', 'TIME'):
            # Observation context items
            val_display = ""
            if vt == 'CODE':
                _, vm, vc, vs = get_code_display(
                    getattr(item, 'ConceptNameCodeSequence', []),
                    getattr(item, 'ConceptCodeSequence', [])
                )
                if vc and vs:
                    val_display = f'{esc(vm)} ({esc(vc)}, {esc(vs)})'
                else:
                    val_display = esc(vm)
            elif vt == 'TEXT':
                val_display = f'"{esc(getattr(item, "TextValue", ""))}"'
            elif vt == 'PNAME':
                pn = str(getattr(item, 'PersonName', ''))
                val_display = esc(pn.replace('^', ' '))
            elif vt in ('DATETIME','DATE','TIME'):
                val_display = esc(str(getattr(item, 'DateTime', getattr(item, 'Date', getattr(item, 'Time', '')))))

            if cn_code and cn_scheme:
                cn_full = f'{esc(cn_meaning)} ({esc(cn_code)}, {esc(cn_scheme)})'
            else:
                cn_full = esc(cn_meaning)

            blocks.append(f'<div class="obs-line">Observation Context: {cn_full} = {val_display}</div>')

    return blocks

# ---- Build HTML ----
patient_name = str(getattr(ds, 'PatientName', '')).replace('^', ' ')
patient_id = getattr(ds, 'PatientID', '')
patient_sex = getattr(ds, 'PatientSex', '')
sex_map = {'M': 'male', 'F': 'female', 'O': 'other'}
sex_display = sex_map.get(str(patient_sex), str(patient_sex))
study_desc = getattr(ds, 'StudyDescription', '')
study_date = getattr(ds, 'StudyDate', '')
study_time_raw = getattr(ds, 'StudyTime', '')
study_id = str(study_date) + str(study_time_raw).split('.')[0]
manufacturer = getattr(ds, 'Manufacturer', '')
model = getattr(ds, 'ManufacturerModelName', '')
serial = getattr(ds, 'DeviceSerialNumber', '')
completion = getattr(ds, 'CompletionFlag', '')
verification = getattr(ds, 'VerificationFlag', '')
content_date = fmt_date(getattr(ds, 'ContentDate', ''))
content_time = fmt_time(getattr(ds, 'ContentTime', ''))

# Root concept
root_concept = "Structured Report"
if hasattr(ds, 'ConceptNameCodeSequence') and ds.ConceptNameCodeSequence:
    root_concept = getattr(ds.ConceptNameCodeSequence[0], 'CodeMeaning', root_concept)

# Render content
content_blocks = render_content_seq(ds.ContentSequence)
content_html = "\n".join(content_blocks)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>DICOM SR - {esc(root_concept)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #ffffff;
    color: #1a1a1a;
    font-family: Arial, Helvetica, sans-serif;
    font-size: 12px;
    line-height: 1.5;
  }}
  .meta-section {{
    padding: 16px 20px 12px 20px;
    border-bottom: 1px solid #ccc;
  }}
  .meta-row {{
    display: flex;
    margin-bottom: 2px;
  }}
  .meta-label {{
    font-weight: bold;
    min-width: 160px;
    color: #1a1a1a;
  }}
  .meta-val {{
    color: #1a1a1a;
  }}
  .separator {{
    border: none;
    border-top: 1px solid #aaa;
    margin: 10px 0;
  }}
  .content-area {{
    padding: 0 20px 20px 20px;
  }}
  .section-header {{
    background: #00b0c8;
    color: #ffffff;
    font-weight: bold;
    font-size: 13px;
    padding: 6px 10px;
    margin: 8px 0 6px 0;
  }}
  .obs-line {{
    color: #1a1a1a;
    font-size: 11.5px;
    margin: 1px 0;
    padding: 0 4px;
  }}
  .meas-block {{
    margin: 6px 0 0 0;
  }}
  .meas-name {{
    font-weight: bold;
    color: #1a1a1a;
    font-size: 12px;
  }}
  .meas-value {{
    color: #1a1a1a;
    font-size: 12px;
    margin-bottom: 2px;
  }}
  .meas-mod {{
    color: #444444;
    font-size: 11px;
    margin: 0;
  }}
  .img-ref {{
    color: #0060a0;
    font-size: 11px;
    margin: 2px 0;
    text-decoration: underline;
  }}
  .uid-small {{
    color: #888;
    font-size: 9px;
    text-decoration: none;
  }}
</style>
</head>
<body>

<div class="meta-section">
  <div class="meta-row"><span class="meta-label">Patient:</span><span class="meta-val">{esc(patient_name)} ({esc(sex_display)}, #{esc(patient_id)})</span></div>
  <div class="meta-row"><span class="meta-label">Study:</span><span class="meta-val">{esc(study_desc)} (#{esc(study_id)})</span></div>
  <div class="meta-row"><span class="meta-label">Protocol:</span><span class="meta-val">{esc(study_desc)}</span></div>
  <div class="meta-row"><span class="meta-label">Manufacturer:</span><span class="meta-val">{esc(manufacturer)} ({esc(model)}, #{esc(serial)})</span></div>
  <div class="meta-row"><span class="meta-label">Completion Flag:</span><span class="meta-val">{esc(str(completion))}</span></div>
  <div class="meta-row"><span class="meta-label">Verification Flag:</span><span class="meta-val">{esc(str(verification))}</span></div>
  <div class="meta-row"><span class="meta-label">Content Date/Time:</span><span class="meta-val">{content_date} {content_time}</span></div>
</div>

<div class="content-area">
  <div class="section-header">{esc(root_concept)}</div>
  {content_html}
</div>

</body>
</html>
"""

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"HTML written: {html_path}")

result = subprocess.run([
    'wkhtmltopdf',
    '--page-size', 'A4',
    '--orientation', 'Portrait',
    '--margin-top', '8mm',
    '--margin-bottom', '8mm',
    '--margin-left', '8mm',
    '--margin-right', '8mm',
    '--enable-local-file-access',
    '--javascript-delay', '200',
    html_path, pdf_path
], capture_output=True, text=True)
print("STDERR:", result.stderr[-500:] if result.stderr else "")
print("Return code:", result.returncode)
if result.returncode == 0:
    size = os.path.getsize(pdf_path)
    print(f"PDF: {pdf_path} ({size} bytes)")
