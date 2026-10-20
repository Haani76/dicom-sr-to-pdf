// Runs the Python converter (dicom_sr_to_pdf) in the browser with Pyodide.
// Files are processed here, in the visitor's browser; nothing is uploaded anywhere.
importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js");

const step = (n, label) => postMessage({ type: "progress", step: n, of: 4, label });

const ready = (async () => {
  step(1, "Starting the Python engine");
  const py = await loadPyodide();
  step(2, "Loading the DICOM reader");
  await py.loadPackage(["micropip", "pillow", "ssl"]);
  const micropip = py.pyimport("micropip");
  await micropip.install(["pydicom==3.0.2", "reportlab==5.0.1", "html5lib", "pypdf", "arabic-reshaper"]);
  step(3, "Loading the PDF writer");
  // xhtml2pdf's svglib dependency needs an lxml newer than Pyodide ships; reports contain no SVG.
  await micropip.install.callKwargs("xhtml2pdf==0.2.26", { deps: false });

  step(4, "Preparing the converter");
  py.FS.mkdirTree("/app/dicom_sr_to_pdf");
  for (const f of ["__init__.py", "report.py"]) {
    const res = await fetch(`dicom_sr_to_pdf/${f}`);
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
