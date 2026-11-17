const $ = (s, e = document) => e.querySelector(s);
const $$ = (s, e = document) => [...e.querySelectorAll(s)];
const api = () => localStorage.api || "http://localhost:8000";
const LANGS = [["en", "English"], ["si", "Sinhala"], ["ta", "Tamil"]];

// Every tool maps to one backend endpoint. m = multiple files, b = shown in Batch, f = extra form fields
const TOOLS = [
  { n: "Image converter", i: "🖼", ep: "/convert/image", acc: ".png,.jpg,.jpeg,.webp,.bmp,.gif",
    f: [{ k: "target_format", l: "Convert to", o: ["png", "jpg", "webp", "bmp", "gif"] }] },
  { n: "PDF to Word", i: "📝", ep: "/convert/pdf-to-word", acc: ".pdf" },
  { n: "Word to PDF", i: "📄", ep: "/convert/word-to-pdf", acc: ".docx,.doc" },
  { n: "Images to PDF", i: "🧾", ep: "/convert/images-to-pdf", acc: ".png,.jpg,.jpeg,.webp", m: 1, b: 1 },
  { n: "Scan to PDF", i: "📷", ep: "/convert/scan-to-pdf", acc: ".png,.jpg,.jpeg,.webp", m: 1, b: 1,
    f: [{ k: "enhance", l: "Sharpen like a scanner", chk: 1 }] },
  { n: "Excel to PDF", i: "📊", ep: "/convert/excel-to-pdf", acc: ".xlsx,.xls" },
  { n: "PDF to Excel", i: "📈", ep: "/convert/pdf-to-excel", acc: ".pdf" },
  { n: "PDF to PowerPoint", i: "🎞", ep: "/convert/pdf-to-pptx", acc: ".pdf" },
  { n: "PowerPoint to PDF", i: "📽", ep: "/convert/pptx-to-pdf", acc: ".pptx,.ppt" },
  { n: "HTML to PDF", i: "🌐", ep: "/convert/html-to-pdf", acc: ".html,.htm" },
  { n: "PDF to images", i: "🏞", ep: "/convert/pdf-to-selected-images", acc: ".pdf",
    f: [{ k: "pages", l: "Pages (optional, e.g. 2, 6)", t: 1 }] },
  { n: "Translate PDF", i: "🈯", ep: "/convert/pdf-translate", acc: ".pdf",
    f: [{ k: "source_lang", l: "From", o: LANGS }, { k: "target_lang", l: "To", o: LANGS, d: "si" }] },
  { n: "Organize pages", i: "🔀", ep: "/convert/organize-pdf", acc: ".pdf",
    f: [{ k: "new_order", l: "New page order (all pages, e.g. 3,1,2)", t: 1, r: 1 }] },
  { n: "Merge PDFs", i: "🧩", ep: "/convert/merge-pdfs", acc: ".pdf", m: 1, b: 1 },
  { n: "Split PDF", i: "✂️", ep: "/convert/split-pdf-links", acc: ".pdf", links: 1,
    f: [{ k: "split_ranges", l: "Ranges (e.g. 1-3, 4-6)", t: 1, r: 1 }] },
  { n: "Compress PDF", i: "🗜", ep: "/convert/compress-pdf", acc: ".pdf" },
];
TOOLS.forEach((t, i) => (t.id = i));

const fmt = b => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const hist = () => JSON.parse(localStorage.hist || "[]");
let toastT;
function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 2600); }

function sheet(title, html) {
  $("#sheet").innerHTML = `<div class="panel"><div class="top"><button class="ic" data-x aria-label="Close">←</button><b>${esc(title)}</b></div><div class="body">${html}</div></div>`;
  $("#sheet").classList.add("on"); $("#sheet").scrollTop = 0;
}
const closeSheet = () => { $("#sheet").classList.remove("on"); renderRecent(); };
const tile = t => `<button class="tile" data-id="${t.id}"><i>${t.i}</i>${t.n}</button>`;

function renderRecent() {
  const h = hist().slice(0, 4);
  $("#recent").innerHTML = h.length ? h.map(rowHtml).join("") : `<p class="empty">Your finished conversions will show up here.</p>`;
}
const rowHtml = h => `<div class="row"><i>🎵</i><div><b>${esc(h.n)}</b><small>${esc(h.t)} · ${fmt(h.s)} · ${new Date(h.d).toLocaleString()}</small></div></div>`.replace("🎵", "📁");

function openHistory() {
  const h = hist();
  sheet("Conversions history", h.length ? h.map(rowHtml).join("") + `<button class="go" id="clr">Clear history</button>` : `<p class="empty">No conversions yet. Pick a tool and convert your first file.</p>`);
  const c = $("#clr"); if (c) c.onclick = () => { localStorage.hist = "[]"; openHistory(); };
}

function openPro() {
  sheet("Go Pro & Packages", `<p>User account for large file conversions:</p>
  
  <div style="background:#f8fafc; padding:15px; border-radius:16px; margin-bottom:10px;">
    <b> Pro Package (Monthly)</b>
    <p style="font-size:13px; color:#64748b; margin:5px 0;">In a month, you can convert up to 100MB of files.</p>
    <button class="go" id="payPro" style="background:#0a58d6; height:45px; font-size:15px;">Get Pro Package (Rs. 2500 / m)</button>
  </div>

  <div style="background:#f8fafc; padding:15px; border-radius:16px; margin-bottom:10px;">
    <b> Micro-payment (Single File)</b>
    <p style="font-size:13px; color:#64748b; margin:5px 0;">Pay only for the files you convert.</p>
    <button class="go" id="payMicro" style="background:#16a34a; height:45px; font-size:15px;">Pay Rs. 25 for a single file</button>
  </div>

  <div id="out"></div>
  <label class="f" style="margin-top:15px;">Server address<input type="text" id="srv" value="${esc(api())}"></label>
  <button class="go" id="save" style="margin-top:10px; height:45px; font-size:15px;">Save server address</button>`);

  $("#save").onclick = () => { localStorage.api = $("#srv").value.replace(/\/$/, ""); toast("Server address saved"); };
  
  // 1. Rs. 2500 Pro Package Checkout
  $("#payPro").onclick = () => handleCheckout("pro");
  
  // 2. Rs. 25 Micro-payment Checkout
  $("#payMicro").onclick = () => handleCheckout("micro");
}

async function handleCheckout(packageType) {
  try {
    // Firebase හෝ Local storage එකෙන් User ID එක ලබා ගැනීම
    localStorage.uid = localStorage.uid || "user_" + Math.random().toString(36).slice(2, 10);
    
    const fd = new URLSearchParams(); 
    fd.append("package_type", packageType); // "micro" හෝ "pro" යැවීම
    
    // (අවශ්‍ය නම් Firebase Token එක Bearer Header එක ලෙස මෙහිදී එකතු කළ හැක)
    const r = await (await fetch(api() + "/api/payment/create-checkout", { 
      method: "POST", 
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: fd 
    })).json();
    
    $("#out").innerHTML = `<a class="dl" href="${esc(r.checkout_url)}" target="_blank" rel="noopener">Open checkout for ${packageType.toUpperCase()} (Rs. ${r.amount})</a>`;
  } catch { 
    $("#out").innerHTML = `<div class="msg er">Cannot reach the server at ${esc(api())}.</div>`; 
  }
}

const send = (url, fd, onp) => new Promise((res, rej) => {
  const x = new XMLHttpRequest(); x.open("POST", url); x.responseType = "blob";
  x.upload.onprogress = e => e.lengthComputable && onp(e.loaded / e.total);
  x.onload = () => res(x);
  x.onerror = () => rej(new Error(`Cannot reach the server at ${api()}. Start the backend and try again.`));
  x.send(fd);
});
async function errText(x) {
  try {
    const d = JSON.parse(await x.response.text()).detail;
    const m = typeof d === "string" ? d : d?.message || JSON.stringify(d);
    return x.status === 402 ? m + " (Rs. 25 payment needed)" : m;
  } catch { return "Conversion failed (error " + x.status + ")."; }
}

function openTool(t, pre) {
  let files = pre ? [pre] : [];
  const fields = (t.f || []).map(f => {
    if (f.chk) return `<label class="c"><input type="checkbox" name="${f.k}" checked>${f.l}</label>`;
    if (f.t) return `<label class="f">${f.l}<input type="text" name="${f.k}" ${f.r ? "required" : ""} autocomplete="off"></label>`;
    const o = f.o.map(v => { const [a, b] = Array.isArray(v) ? v : [v, v.toUpperCase()]; return `<option value="${a}" ${f.d === a ? "selected" : ""}>${b}</option>`; }).join("");
    return `<label class="f">${f.l}<select name="${f.k}">${o}</select></label>`;
  }).join("");
  sheet(t.n, `<div class="drop" id="dz" tabindex="0" role="button">Tap or drop ${t.m ? "files" : "a file"} here<small>${t.acc}</small></div>
    <input id="fi" type="file" hidden ${t.m ? "multiple" : ""} accept="${t.acc}"><div id="fl"></div>${fields}
    <button class="go" id="run">Convert</button><div class="bar2" id="pb" hidden><span></span></div><div id="out"></div>`);

  const list = () => {
    $("#fl").innerHTML = files.map((f, i) => `<div class="row"><i>📁</i><div><b>${esc(f.name)}</b><small>${fmt(f.size)}</small></div><button class="x" data-rm="${i}" aria-label="Remove">×</button></div>`).join("");
    $$("[data-rm]").forEach(b => b.onclick = () => { files.splice(+b.dataset.rm, 1); list(); });
  };
  const add = fl => { files = t.m ? files.concat([...fl]) : [fl[0]]; list(); };
  const dz = $("#dz"), fi = $("#fi");
  dz.onclick = () => fi.click(); dz.onkeydown = e => (e.key === "Enter" || e.key === " ") && fi.click();
  fi.onchange = () => { add(fi.files); fi.value = ""; };
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); add(e.dataTransfer.files); };
  list();

  $("#run").onclick = async () => {
    const out = $("#out"), btn = $("#run"), pb = $("#pb");
    if (!files.length) return (out.innerHTML = `<div class="msg er">Choose ${t.m ? "at least one file" : "a file"} first.</div>`);
    const fd = new FormData();
    files.forEach(f => fd.append(t.m ? "files" : "file", f));
    for (const e of $$("#sheet [name]")) {
      if (e.required && !e.value.trim()) return (out.innerHTML = `<div class="msg er">Fill in: ${esc(e.closest("label").textContent)}</div>`);
      fd.append(e.name, e.type === "checkbox" ? e.checked : e.value.trim());
    }
    btn.disabled = true; btn.textContent = "Converting…"; out.innerHTML = ""; pb.hidden = false;
    const bar = pb.firstElementChild; bar.style.width = "0";
    try {
      const x = await send(api() + t.ep, fd, p => (bar.style.width = p * 100 + "%"));
      bar.style.width = "100%";
      if (x.status >= 300) throw new Error(await errText(x));
      let html;
      if (/json/.test(x.getResponseHeader("content-type") || "")) {
        const j = JSON.parse(await x.response.text());
        html = `<div class="msg ok">Split into ${j.parts.length} part(s).</div>` +
          j.parts.map(p => `<a class="dl" href="${esc(p.url)}" target="_blank" rel="noopener">Download ${esc(p.title)}</a>`).join("") +
          `<a class="dl" href="${esc(j.download_all_url)}" target="_blank" rel="noopener">Download all (ZIP)</a>`;
      } else {
        const m = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(x.getResponseHeader("content-disposition") || "");
        const name = m ? decodeURIComponent(m[1]) : "converted-file";
        const url = URL.createObjectURL(x.response);
        html = `<div class="msg ok">Done. ${fmt(x.response.size)} ready.</div><a class="dl" href="${url}" download="${esc(name)}">Download ${esc(name)}</a>`;
      }
      out.innerHTML = html;
      localStorage.hist = JSON.stringify([{ n: files.length > 1 ? `${files[0].name} +${files.length - 1} more` : files[0].name, t: t.n, s: files.reduce((a, f) => a + f.size, 0), d: Date.now() }, ...hist()].slice(0, 50));
    } catch (e) { out.innerHTML = `<div class="msg er">${esc(e.message)}</div>`; }
    btn.disabled = false; btn.textContent = "Convert"; setTimeout(() => (pb.hidden = true), 600);
  };
}

function quickPick(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  const m = TOOLS.filter(t => t.acc.split(",").includes(ext));
  if (!m.length) return toast("This file type is not supported yet");
  if (m.length === 1) return openTool(m[0], file);
  window.picked = file;
  sheet("Convert " + file.name, `<div class="grid" style="padding:0">${m.map(tile).join("")}</div>`);
}

document.addEventListener("click", e => {
  if (e.target.closest("[data-x]") || e.target.id === "sheet") return closeSheet();
  const t = e.target.closest("[data-id]");
  if (t) { const tool = TOOLS[+t.dataset.id]; openTool(tool, window.picked && tool.acc.includes("." + window.picked.name.split(".").pop().toLowerCase()) ? window.picked : null); window.picked = null; }
});
$("#tools").innerHTML = TOOLS.map(tile).join("");
$("#quick").onclick = () => $("#qf").click();
$("#qf").onchange = e => { if (e.target.files[0]) quickPick(e.target.files[0]); e.target.value = ""; };
$("#goBatch").onclick = () => sheet("Batch conversions", `<p>Work with many files in one go.</p><div class="grid" style="padding:0">${TOOLS.filter(t => t.b).map(tile).join("")}</div>`);
$("#goHist").onclick = $("#menu").onclick = openHistory;
$("#navBatch").onclick = () => $("#goBatch").click();
document.addEventListener("keydown", e => e.key === "Escape" && closeSheet());
$("#pro").onclick = openPro;
renderRecent();
