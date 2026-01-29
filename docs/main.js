const statusEl = document.getElementById("status");
const termEl = document.getElementById("terminal");
const manifestUrl = new URL("asset-manifest.json", window.location.href);
const rootUrl = new URL(".", window.location.href);

const term = new Terminal({
  cols: 100,
  rows: 30,
  convertEol: true,
  cursorBlink: false,
  lineHeight: 1.0,
  fontFamily: "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  fontSize: 14,
  theme: {
    background: "#050607",
    foreground: "#e8e4dc",
  },
});

initTerminal();

async function initTerminal() {
  await waitForFonts();
  term.open(termEl);
  term.write("Booting runtime...\r\n");
  sizeTerminalToGrid();
  window.addEventListener("resize", () => sizeTerminalToGrid());
  bootPyodide().catch((err) => {
    writeToTerminal(`\x1b[31mBoot error: ${err}\x1b[0m\r\n`);
    setStatus("Boot failed. Check console.");
    console.error(err);
  });
}

function writeToTerminal(text) {
  if (!text) return;
  const normalized = text.replace(/\n/g, "\r\n");
  term.write(normalized);
}

function setStatus(text) {
  if (statusEl) statusEl.textContent = text;
}

function measureCharSize() {
  const probe = document.createElement("span");
  probe.textContent = "M";
  probe.style.fontFamily = term.options.fontFamily || "monospace";
  probe.style.fontSize = `${term.options.fontSize || 14}px`;
  probe.style.position = "absolute";
  probe.style.visibility = "hidden";
  document.body.appendChild(probe);
  const rect = probe.getBoundingClientRect();
  probe.remove();
  return { width: rect.width, height: rect.height };
}

function waitForFonts() {
  if (!document.fonts?.load) {
    return Promise.resolve();
  }
  const fontFamily = term.options.fontFamily || "monospace";
  const fontSize = term.options.fontSize || 14;
  const load = document.fonts.load(`${fontSize}px ${fontFamily}`);
  const ready = document.fonts.ready;
  const timeout = new Promise((resolve) => setTimeout(resolve, 1500));
  return Promise.race([Promise.all([load, ready]), timeout]);
}

function sizeTerminalToGrid() {
  if (sizeTerminalToGrid._busy) return;
  sizeTerminalToGrid._busy = true;
  requestAnimationFrame(() => {
    _sizeTerminalToGrid();
  });
}

function _sizeTerminalToGrid() {
  let cellWidth = 0;
  let cellHeight = 0;
  const dims = term._core?._renderService?.dimensions;
  if (dims?.css?.cell) {
    cellWidth = dims.css.cell.width;
    cellHeight = dims.css.cell.height;
  } else {
    const measured = measureCharSize();
    const fontSize = term.options.fontSize || 14;
    const lineHeight = term.options.lineHeight || 1;
    cellWidth = measured.width;
    cellHeight = Math.max(measured.height, fontSize * lineHeight);
  }
  const borderPad = 2;
  const safetyPad = 4;
  let targetWidth = Math.ceil(cellWidth * term.cols) + borderPad + safetyPad;
  let targetHeight = Math.ceil(cellHeight * term.rows) + borderPad + safetyPad;

  termEl.style.width = `${targetWidth}px`;
  termEl.style.height = `${targetHeight}px`;
  term.resize(term.cols, term.rows);
  requestAnimationFrame(() => {
    const screen = termEl.querySelector(".xterm-screen");
    if (screen) {
      const rect = screen.getBoundingClientRect();
      const minWidth = Math.ceil(rect.width) + borderPad + safetyPad;
      const minHeight = Math.ceil(rect.height) + borderPad + safetyPad;
      const finalWidth = Math.max(targetWidth, minWidth);
      const finalHeight = Math.max(targetHeight, minHeight);
      if (finalWidth !== targetWidth || finalHeight !== targetHeight) {
        termEl.style.width = `${finalWidth}px`;
        termEl.style.height = `${finalHeight}px`;
      }
    }
    sizeTerminalToGrid._busy = false;
  });
}

function ensureDir(fs, dirPath) {
  if (!dirPath || dirPath === "/") return;
  const parts = dirPath.split("/").filter(Boolean);
  let current = "";
  for (const part of parts) {
    current += `/${part}`;
    if (!fs.analyzePath(current).exists) {
      fs.mkdir(current);
    }
  }
}

async function fetchManifest() {
  const response = await fetch(manifestUrl);
  if (!response.ok) {
    throw new Error(`Failed to load manifest: ${response.status}`);
  }
  return response.json();
}

async function loadAssets(pyodide, manifest) {
  const { FS } = pyodide;
  for (const file of manifest.files || []) {
    const fileUrl = new URL(file, rootUrl);
    const response = await fetch(fileUrl);
    if (!response.ok) {
      throw new Error(`Failed to fetch ${file} (${response.status})`);
    }
    const text = await response.text();
    const dir = `/${file.split("/").slice(0, -1).join("/")}`;
    ensureDir(FS, dir);
    FS.writeFile(`/${file}`, text);
  }
}

function mapKeyEvent(domEvent) {
  switch (domEvent.key) {
    case "ArrowLeft":
      return "LEFT";
    case "ArrowRight":
      return "RIGHT";
    case "ArrowUp":
      return "UP";
    case "ArrowDown":
      return "DOWN";
    case "Enter":
      return "ENTER";
    default:
      break;
  }
  if (domEvent.key && domEvent.key.length === 1) {
    return domEvent.key;
  }
  return "";
}

async function bootPyodide() {
  setStatus("Loading Pyodide...");
  const pyodide = await loadPyodide({
    indexURL: "https://cdn.jsdelivr.net/pyodide/v0.29.2/full/",
    stdout: (text) => writeToTerminal(text),
    stderr: (text) => writeToTerminal(`\x1b[31m${text}\x1b[0m`),
  });
  window.pyodide = pyodide;
  writeToTerminal("Pyodide ready.\r\n");

  setStatus("Loading asset manifest...");
  const manifest = await fetchManifest();
  writeToTerminal(`Loading assets (${manifest.files.length})...\r\n`);
  await loadAssets(pyodide, manifest);

  setStatus("Mounting save storage...");
  const { FS } = pyodide;
  ensureDir(FS, "/saves");
  FS.mount(FS.filesystems.IDBFS, {}, "/saves");
  await new Promise((resolve, reject) => {
    FS.syncfs(true, (err) => (err ? reject(err) : resolve()));
  });
  window.syncSaves = () =>
    new Promise((resolve, reject) => {
      FS.syncfs(false, (err) => (err ? reject(err) : resolve()));
    });

  setStatus("Configuring input bridge...");
  FS.chdir("/");
  await pyodide.runPythonAsync(
    [
      "import sys",
      "sys.path.insert(0, '/')",
      "import os",
      "os.environ['LOKARTA_WEB'] = '1'",
      "os.environ['COLUMNS'] = '100'",
      "os.environ['LINES'] = '30'",
      "import app.input as input_mod",
      "input_mod.enable_browser_input()",
      "enqueue_key = input_mod.enqueue_key",
    ].join("\n")
  );
  const enqueueKey = pyodide.globals.get("enqueue_key");

  term.onKey(({ domEvent }) => {
    const mapped = mapKeyEvent(domEvent);
    if (mapped) {
      enqueueKey(mapped);
    }
    domEvent.preventDefault();
  });

  setStatus("Launching game...");
  writeToTerminal("Launching game...\r\n");
  pyodide.runPythonAsync("import main; main.main()").catch((err) => {
    writeToTerminal(`\x1b[31mRuntime error: ${err}\x1b[0m\r\n`);
    setStatus("Runtime error. Check console.");
    console.error(err);
  });
}
