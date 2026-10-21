// Runs the Python converter (dicom_sr_to_pdf) in the browser with Pyodide.
// app.js starts this from a blob: URL, so the page's Content-Security-Policy also governs this
// worker (no network access except this site), and prepends `const BASE = "<site url>"`.
// Every file below comes from this site and was hash-checked at build time (web/vendor-lock.json).
importScripts(BASE + "pyodide/pyodide.js");

const step = (n, label) => postMessage({ type: "progress", step: n, of: 4, label });

const ready = (async () => {
  step(1, "Starting the Python engine");
  const py = await loadPyodide({ indexURL: BASE + "pyodide/" });
  step(2, "Loading the DICOM reader");
  await py.loadPackage(["pillow", "ssl", "html5lib", "charset-normalizer"]);
  const { wheels } = await (await fetch(BASE + "vendor.json")).json();
  step(3, "Loading the PDF writer");
  // xhtml2pdf's optional svglib dependency is not shipped; reports contain no SVG.
  await py.loadPackage(wheels.map((w) => BASE + "wheels/" + w));

  step(4, "Preparing the converter");
  py.FS.mkdirTree("/app/dicom_sr_to_pdf");
  for (const f of ["__init__.py", "report.py"]) {
    const res = await fetch(`${BASE}dicom_sr_to_pdf/${f}`);
    if (!res.ok) throw new Error(`could not load converter file ${f} (${res.status})`);
    py.FS.writeFile(`/app/dicom_sr_to_pdf/${f}`, await res.text());
  }
  py.runPython(`
import io, sys, zipfile
sys.path.insert(0, "/app")
from pydicom.errors import InvalidDicomError
from dicom_sr_to_pdf import __version__
from dicom_sr_to_pdf.report import render

def convert(data, details):
    try:
        html, pdf, missing = render(io.BytesIO(data.to_py().tobytes()), details)
    except InvalidDicomError:
        return {"status": "skip", "message": "not a DICOM file"}
    except ValueError as e:
        return {"status": "skip", "message": str(e)}
    except Exception as e:  # report and continue with the next file
        return {"status": "fail", "message": f"{type(e).__name__}: {e}"}
    return {"status": "ok", "pdf": memoryview(pdf), "missing": missing}

def make_zip(names, pdfs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, pdf in zip(names.to_py(), pdfs.to_py()):
            z.writestr(name, bytes(pdf))
    return memoryview(buf.getvalue())
`);
  return py;
})();

ready.then(
  (py) => postMessage({ type: "ready", version: py.globals.get("__version__") }),
  (e) => postMessage({ type: "fatal", message: String(e) }),
);

onmessage = async ({ data }) => {
  const py = await ready;
  if (data.type === "convert") {
    const result = py.globals.get("convert")(data.bytes, data.details);
    const status = result.get("status");
    const out = { type: "result", id: data.id, status, message: result.get("message") };
    if (status === "ok") {
      out.pdf = result.get("pdf").toJs();           // Uint8Array copy
      out.missing = result.get("missing").toJs();
    }
    result.destroy();
    postMessage(out, out.pdf ? [out.pdf.buffer] : []);
  } else if (data.type === "zip") {
    try {
      const zip = py.globals.get("make_zip")(data.names, data.pdfs).toJs();
      postMessage({ type: "zip", zip }, [zip.buffer]);
    } catch (e) {
      postMessage({ type: "zip-error", message: String(e).trim().split("\n").pop() });
    }
  }
};
