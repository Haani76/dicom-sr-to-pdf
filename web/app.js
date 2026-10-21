// DICOM SR to PDF web app: file handling, results, preview. Conversion happens in worker.js.
const $ = (id) => document.getElementById(id);
// The worker runs from a blob: URL so it inherits this page's Content-Security-Policy
// (a worker loaded from its own URL on GitHub Pages would get no policy at all).
const BASE = new URL(".", location.href).href;
let worker;
(async () => {
  try {
    const src = await (await fetch("worker.js")).text();
    const blob = new Blob([`const BASE = ${JSON.stringify(BASE)};\n`, src], { type: "text/javascript" });
    worker = new Worker(URL.createObjectURL(blob));
    worker.onmessage = onWorkerMessage;
  } catch (e) {
    onWorkerMessage({ data: { type: "fatal", message: String(e) } });
  }
})();
const items = new Map();      // id -> {name, li, pdf?, url?}
const queue = [];             // ids waiting for the worker
let ready = false, busy = false, nextId = 0, previewId = null;

const loadStart = performance.now();
const clock = setInterval(() => {
  $("eng-time").textContent = `(${Math.round((performance.now() - loadStart) / 1000)} s)`;
}, 1000);

function onWorkerMessage({ data }) {
  if (data.type === "progress") {
    $("eng-text").innerHTML = `<span class="spin"></span> ${data.label}… <small>step ${data.step} of ${data.of}</small>`;
    $("eng-bar").style.width = `${(data.step - 0.5) / data.of * 100}%`;
  } else if (data.type === "ready") {
    ready = true;
    clearInterval(clock);
    $("engine").className = "engine ready";
    const secs = ((performance.now() - loadStart) / 1000).toFixed(1);
    $("engine").textContent = `✓ Converter ready (loaded in ${secs} s).`;
    $("ver").textContent = `· Converter v${data.version}`;
    pump();
  } else if (data.type === "fatal") {
    clearInterval(clock);
    $("engine").className = "engine fatal";
    $("engine").textContent = "The converter could not load. Check your internet connection and reload the page. (" + data.message.split("\n").pop() + ")";
  } else if (data.type === "result") {
    finish(data);
    busy = false;
    pump();
  } else if (data.type === "zip") {
    save(new Blob([data.zip], { type: "application/zip" }), "sr-reports.zip");
  } else if (data.type === "zip-error") {
    alert("Could not build the zip: " + data.message);
  }
}

function pdfName(name) {
  return name.replace(/\.(dcm|dicom)$/i, "") + ".pdf";
}

function add(files) {
  if (!files.length) return;
  $("results").hidden = false;
  for (const file of files) {
    const id = nextId++;
    const li = document.createElement("li");
    li.innerHTML = `<div><div class="fname"></div><div class="fmsg"><span class="spin"></span> ${ready ? "Waiting…" : "Waiting for the converter to load…"}</div></div><div class="actions"></div>`;
    li.querySelector(".fname").textContent = file.webkitRelativePath || file.relPath || file.name;
    const rm = Object.assign(document.createElement("button"), { type: "button", textContent: "Remove" });
    rm.setAttribute("aria-label", "Remove " + file.name + " and its PDF from this page");
    rm.onclick = () => remove(id);
    li.querySelector(".actions").append(rm);
    $("list").append(li);
    items.set(id, { name: file.name, file, li });
    queue.push(id);
  }
  pump();
}

async function pump() {
  if (!ready || busy || !queue.length) return;
  busy = true;
  const id = queue.shift();
  const it = items.get(id);
  if (!it) { busy = false; return pump(); }   // cleared meanwhile
  it.li.querySelector(".fmsg").innerHTML = '<span class="spin"></span> Converting…';
  const bytes = new Uint8Array(await it.file.arrayBuffer());
  worker.postMessage({ type: "convert", id, bytes, details: $("details").checked }, [bytes.buffer]);
}

function finish({ id, status, message, pdf, missing }) {
  const it = items.get(id);
  if (!it) return;
  const msg = it.li.querySelector(".fmsg");
  if (status === "ok") {
    it.pdf = pdf;
    it.url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
    const pages = (new TextDecoder("latin1").decode(pdf).match(/\/Type\s*\/Page[^s]/g) || []).length;
    if (missing.length) {
      it.li.className = "st-warn";
      msg.textContent = `⚠ Converted, but not shown in PDF: ${missing.join(", ")}`;
    } else {
      it.li.className = "st-ok";
      msg.textContent = `✓ Converted · ${pages} page${pages === 1 ? "" : "s"} · everything in the SR is included`;
    }
    const acts = it.li.querySelector(".actions");
    const view = Object.assign(document.createElement("button"), { type: "button", textContent: "View" });
    view.onclick = () => show(id);
    const dl = Object.assign(document.createElement("a"), { className: "btn", href: it.url, download: pdfName(it.name), textContent: "Download" });
    acts.prepend(view, dl);
    if (previewId === null) show(id);
  } else {
    it.li.className = status === "skip" ? "" : "st-fail";
    msg.textContent = status === "skip" ? `Skipped: ${message}` : `✗ Failed: ${message}`;
  }
  $("zip").disabled = ![...items.values()].some((i) => i.pdf);
}

// Drop every trace of a file: list row, preview, PDF data and its blob URL.
function remove(id) {
  const it = items.get(id);
  if (!it) return;
  if (it.url) URL.revokeObjectURL(it.url);
  it.li.remove();
  items.delete(id);
  const q = queue.indexOf(id);
  if (q >= 0) queue.splice(q, 1);
  if (previewId === id) {
    previewId = null;
    $("preview").classList.remove("show");
    $("pv-frame").removeAttribute("src");
    $("pv-open").removeAttribute("href");
    $("pv-dl").removeAttribute("href");
  }
  if (!items.size) $("results").hidden = true;
  $("zip").disabled = ![...items.values()].some((i) => i.pdf);
}

function show(id) {
  const it = items.get(id);
  previewId = id;
  $("preview").classList.add("show");
  $("pv-frame").src = it.url;
  $("pv-open").href = it.url;
  $("pv-dl").href = it.url;
  $("pv-dl").download = pdfName(it.name);
  $("pv-h").textContent = "Preview: " + pdfName(it.name);
}

function save(blob, name) {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

$("zip").onclick = () => {
  const done = [...items.values()].filter((i) => i.pdf);
  const names = [], seen = new Map();
  for (const i of done) {   // keep names unique inside the zip
    let n = pdfName(i.name);
    const k = seen.get(n) || 0;
    seen.set(n, k + 1);
    if (k) n = n.replace(/\.pdf$/, ` (${k + 1}).pdf`);
    names.push(n);
  }
  worker.postMessage({ type: "zip", names, pdfs: done.map((i) => i.pdf) });
};

$("clear").onclick = () => { for (const id of [...items.keys()]) remove(id); };
$("pv-rm").onclick = () => remove(previewId);

$("pick-files").onclick = () => $("files").click();
$("pick-folder").onclick = () => $("folder").click();
$("files").onchange = (e) => { add([...e.target.files]); e.target.value = ""; };
$("folder").onchange = (e) => { add([...e.target.files]); e.target.value = ""; };

// Drag and drop, including whole folders.
const drop = $("drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
drop.addEventListener("drop", async (e) => {
  e.preventDefault();
  const entries = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return add([...e.dataTransfer.files]);
  const files = [];
  async function walk(entry, path) {
    if (entry.isFile) {
      const f = await new Promise((res, rej) => entry.file(res, rej));
      f.relPath = path + f.name;
      files.push(f);
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {   // readEntries returns results in chunks
        batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        for (const child of batch) await walk(child, path + entry.name + "/");
      } while (batch.length);
    }
  }
  for (const entry of entries) await walk(entry, "");
  add(files);
});
