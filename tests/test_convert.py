"""End-to-end tests on a synthetic SR (fake patient, no real data)."""
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dicom_sr_to_pdf.cli import main
from dicom_sr_to_pdf.report import build_html, missing_values


def cd(value, scheme, meaning):
    c = Dataset()
    c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = value, scheme, meaning
    return Sequence([c])


def item(vt, rel, name, **kw):
    it = Dataset()
    it.ValueType, it.RelationshipType = vt, rel
    it.ConceptNameCodeSequence = cd(*name)
    for k, v in kw.items():
        setattr(it, k, v)
    return it


def num(name, value, unit, mods=()):
    mv = Dataset()
    mv.NumericValue, mv.MeasurementUnitsCodeSequence = value, cd(unit, "UCUM", unit)
    children = [item("CODE", "HAS CONCEPT MOD", m[0], ConceptCodeSequence=cd(*m[1])) for m in mods]
    return item("NUM", "CONTAINS", name, MeasuredValueSequence=Sequence([mv]),
                **({"ContentSequence": Sequence(children)} if children else {}))


def make_sr(path):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.33"
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.Modality = "SR"
    ds.PatientName, ds.PatientID, ds.PatientSex = "Test^Jane", "T-001", "F"
    ds.StudyDescription, ds.StudyDate, ds.StudyTime = "Carotid Duplex", "20260115", "093000"
    ds.ContentDate, ds.ContentTime = "20260115", "094512"
    ds.Manufacturer, ds.ManufacturerModelName = "Acme", "US-1"
    ds.CompletionFlag, ds.VerificationFlag = "COMPLETE", "UNVERIFIED"
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = cd("125100", "DCM", "Vascular Ultrasound Procedure Report")
    img = Dataset()
    img.ReferencedSOPClassUID, img.ReferencedSOPInstanceUID = "1.2.840.10008.5.1.4.1.1.6.1", "1.2.3.4"
    section = item("CONTAINER", "CONTAINS", ("121070", "DCM", "Findings"), ContentSequence=Sequence([
        item("CODE", "HAS OBS CONTEXT", ("G-C0E3", "SRT", "Finding Site"),
             ConceptCodeSequence=cd("T-45010", "SRT", "Carotid Artery")),
        num(("11726-7", "LN", "Peak Systolic Velocity"), "85.300000", "cm/s"),  # raw reading
        num(("11726-7", "LN", "Peak Systolic Velocity"), "85.3", "cm/s",
            mods=[(("G-C171", "SRT", "Laterality"), ("G-A100", "SRT", "Right"))]),
        num(("11653-3", "LN", "End Diastolic Velocity"), "22.1", "cm/s"),
        item("IMAGE", "INFERRED FROM", ("121112", "DCM", "Source"), ReferencedSOPSequence=Sequence([img])),
    ]))
    ds.ContentSequence = Sequence([section])
    ds.save_as(path, enforce_file_format=True)
    return ds


def test_html_has_header_table_and_modifiers(tmp_path):
    html = build_html(make_sr(tmp_path / "a.dcm"))
    for text in ("Vascular Ultrasound Procedure Report", "Jane Test", "Findings",
                 "Peak Systolic Velocity", "85.3", "cm/s", "Laterality: Right",
                 "Carotid Artery", "Referenced: Source (Image)"):
        assert text in html, text
    assert "1.2.3.4" not in html and "(G-A100, SRT)" not in html
    assert html.count("Peak Systolic Velocity") == 1 and "85.300000" not in html
    detailed = build_html(make_sr(tmp_path / "b.dcm"), details=True)
    assert "1.2.3.4" in detailed and "G-A100" in detailed
    assert detailed.count("Peak Systolic Velocity") == 2


def test_batch_folder_skips_non_sr(tmp_path):
    src = tmp_path / "in"
    (src / "sub").mkdir(parents=True)
    make_sr(src / "one.dcm")
    make_sr(src / "sub" / "two")  # no extension, nested
    (src / "notes.txt").write_text("not dicom")
    out = tmp_path / "out"
    assert main([str(src), "-o", str(out)]) == 0
    for name in ("one.pdf", "two.pdf"):
        pdf = (out / name).read_bytes()
        assert pdf.startswith(b"%PDF") and len(pdf) > 2000


def test_single_file_explicit_output(tmp_path):
    make_sr(tmp_path / "r.dcm")
    assert main([str(tmp_path / "r.dcm"), "-o", str(tmp_path / "x" / "report.pdf"), "--html"]) == 0
    assert (tmp_path / "x" / "report.pdf").exists() and (tmp_path / "x" / "report.html").exists()


def test_details_view_contains_every_value(tmp_path):
    ds = make_sr(tmp_path / "a.dcm")
    assert missing_values(ds, build_html(ds, details=True), details=True) == []
    assert missing_values(ds, build_html(ds)) == []


def make_complex_sr(path):
    """SR using the less common content: coordinates, nesting under non-containers, by-reference."""
    ds = make_sr(path)
    img = Dataset()
    img.ReferencedSOPClassUID, img.ReferencedSOPInstanceUID = "1.2.840.10008.5.1.4.1.1.6.1", "9.9.9"
    img.ReferencedFrameNumber = [3]
    outline = item("SCOORD", "INFERRED FROM", ("111030", "DCM", "Image Region"),
                   GraphicType="POLYLINE", GraphicData=[1.0, 2.0, 3.0, 4.0],
                   ContentSequence=Sequence([item("IMAGE", "SELECTED FROM", ("121112", "DCM", "Source"),
                                                  ReferencedSOPSequence=Sequence([img]))]))
    nan = Dataset()
    nan_item = item("NUM", "CONTAINS", ("1", "99X", "Plaque Area"),
                    MeasuredValueSequence=Sequence([]), NumericValueQualifierCodeSequence=cd("114000", "DCM", "Not a number"),
                    ContentSequence=Sequence([outline]))
    finding = item("CODE", "CONTAINS", ("121071", "DCM", "Finding"), ConceptCodeSequence=cd("1", "99X", "Stenosis"),
                   ContentSequence=Sequence([
                       item("TEXT", "HAS PROPERTIES", ("121106", "DCM", "Comment"), TextValue="Mild narrowing"),
                       item("TCOORD", "INFERRED FROM", ("2", "99X", "Cardiac Phase"),
                            TemporalRangeType="POINT", ReferencedTimeOffsets=[0.25])]))
    composite = item("COMPOSITE", "CONTAINS", ("3", "99X", "Prior Report"), ReferencedSOPSequence=Sequence([img]))
    byref = Dataset()
    byref.RelationshipType, byref.ReferencedContentItemIdentifier = "INFERRED FROM", [1, 1, 2]
    odd = item("FUTURETYPE", "CONTAINS", ("4", "99X", "Strange Item"))
    ds.ContentSequence[0].ContentSequence.extend([nan_item, finding, composite, byref, odd])
    del nan
    ds.save_as(path, enforce_file_format=True)
    return ds


def test_uncommon_content_is_rendered_and_unknown_is_reported(tmp_path):
    ds = make_complex_sr(tmp_path / "c.dcm")
    html = build_html(ds, details=True)
    for text in ("Plaque Area", "Not a number", "Image Region", "POLYLINE (2 points)", "9.9.9", "frames 3",
                 "Finding", "Stenosis", "Mild narrowing", "Cardiac Phase", "POINT", "0.25",
                 "Prior Report", "see content item 1.1.2", "Strange Item", "unsupported value type FUTURETYPE"):
        assert text in html, text
    assert missing_values(ds, html, details=True) == ["unsupported item type FUTURETYPE"]
    assert "All DICOM attributes" in html and "StudyDescription" in html
    plain = build_html(ds)
    assert "All DICOM attributes" not in plain and "Comment: Mild narrowing" in plain
    assert "Prior Report (Referenced object)" in plain


def test_cli_warns_about_unshown_content(tmp_path, capsys):
    make_complex_sr(tmp_path / "c.dcm")
    assert main([str(tmp_path / "c.dcm")]) == 0
    assert "not shown in PDF: unsupported item type FUTURETYPE" in capsys.readouterr().err
