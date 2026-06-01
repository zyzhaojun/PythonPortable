from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = BASE_DIR / "run_outputs"
MPL_CACHE = BASE_DIR / "matplotlib_cache"
RUNNER = BASE_DIR / "runner.py"
TIMEOUT_SECONDS = 60
INTERACTIVE_SESSION_TTL = 15 * 60

RUNTIMES = {
    "3.7": BASE_DIR / "runtimes" / "python37" / "python.exe",
    "3.12": BASE_DIR / "runtimes" / "python312" / "python.exe",
}

SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()


class PortableThreadingHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # Avoid HTTPServer.server_bind calling socket.getfqdn(), which can fail
        # on older Chinese Windows machines while Python is running in UTF-8 mode.
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)

HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>便携 Python 教学运行台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --line: #d8dee6;
      --text: #1f2933;
      --muted: #667085;
      --brand: #2166a5;
      --brand-strong: #154b7d;
      --ok: #1f7a4d;
      --bad: #b42318;
      --code: #ffffff;
      --code-text: #1e1e1e;
      --code-line: #d7e8ff;
      --code-gutter: #f3f8ff;
      --selection: #add6ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
    }
    .topbar {
      min-height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 18px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .brand-mark {
      width: 36px;
      height: 36px;
      display: grid;
      place-items: center;
      border-radius: 6px;
      background: var(--brand);
      color: #fff;
      font-weight: 700;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 700;
    }
    .runtime-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .runtime-tabs {
      display: inline-grid;
      grid-template-columns: repeat(2, minmax(98px, 1fr));
      border: 1px solid var(--line);
      border-radius: 7px;
      overflow: hidden;
      background: #eef2f6;
    }
    .runtime-tabs button {
      min-height: 36px;
      border: 0;
      border-right: 1px solid var(--line);
      padding: 0 12px;
      background: transparent;
      color: var(--text);
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }
    .runtime-tabs button:last-child { border-right: 0; }
    .runtime-tabs button.active {
      background: var(--brand);
      color: #fff;
    }
    .runtime-status {
      min-width: 176px;
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(420px, 1fr) minmax(420px, 1fr);
      gap: 12px;
      height: calc(100vh - 58px);
      padding: 12px;
    }
    .pane {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
    }
    .pane-head {
      min-height: 45px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .pane-title {
      font-weight: 700;
      white-space: nowrap;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    button.command {
      min-height: 34px;
      border: 1px solid var(--brand-strong);
      border-radius: 6px;
      padding: 0 14px;
      background: var(--brand);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button.command:disabled {
      opacity: .58;
      cursor: not-allowed;
    }
    button.secondary {
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      background: #fff;
      color: var(--text);
      font: inherit;
      cursor: pointer;
    }
    .editor-wrap {
      flex: 1;
      min-height: 0;
      display: flex;
      background: var(--code);
      border-left: 4px solid #007acc;
      box-shadow: inset 0 1px 0 var(--code-line);
      overflow: hidden;
    }
    .editor-wrap:focus-within {
      border-left-color: #0066b8;
      box-shadow: inset 0 0 0 2px #9cdcfe;
    }
    .gutter {
      flex: 0 0 auto;
      min-width: 3ch;
      padding: 14px 8px 14px 10px;
      text-align: right;
      background: var(--code-gutter);
      color: #93a1b0;
      font: 15px/1.55 Consolas, "Cascadia Mono", "Courier New", monospace;
      white-space: pre;
      overflow: hidden;
      user-select: none;
      border-right: 1px solid var(--code-line);
    }
    .editor {
      flex: 1;
      min-height: 0;
      width: 100%;
      resize: none;
      border: 0;
      padding: 14px 16px;
      background: var(--code);
      color: var(--code-text);
      font: 15px/1.55 Consolas, "Cascadia Mono", "Courier New", monospace;
      outline: none;
      tab-size: 4;
      caret-color: #007acc;
    }
    .editor::selection {
      background: var(--selection);
      color: #1e1e1e;
    }
    .output {
      flex: 1;
      min-height: 0;
      overflow: auto;
      padding: 12px;
      background: #f8fafc;
    }
    pre {
      margin: 0 0 10px;
      white-space: pre-wrap;
      word-break: break-word;
      border-radius: 6px;
      padding: 10px;
      background: #111827;
      color: #e5e7eb;
      font: 14px/1.5 Consolas, "Cascadia Mono", "Courier New", monospace;
    }
    pre.stderr {
      background: #fff1f1;
      color: var(--bad);
      border: 1px solid #f2b8b5;
    }
    pre.feedback {
      background: #eef7f1;
      color: var(--ok);
      border: 1px solid #b8dec8;
    }
    .runtime-html {
      overflow: auto;
      margin-bottom: 10px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
      padding: 8px;
    }
    table.data-frame {
      border-collapse: collapse;
      font-size: 13px;
      min-width: 100%;
    }
    table.data-frame th,
    table.data-frame td {
      border: 1px solid var(--line);
      padding: 5px 7px;
      text-align: right;
    }
    table.data-frame th {
      background: #edf2f7;
      font-weight: 700;
    }
    figure {
      margin: 0 0 10px;
      padding: 10px;
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 6px;
    }
    figure img {
      max-width: 100%;
      display: block;
    }
    .terminal {
      min-height: 120px;
      margin: 0 0 10px;
      white-space: pre-wrap;
      word-break: break-word;
      border-radius: 6px;
      padding: 10px;
      background: #ffffff;
      color: #1e1e1e;
      border: 1px solid var(--line);
      font: 14px/1.5 Consolas, "Cascadia Mono", "Courier New", monospace;
    }
    .terminal-input {
      width: min(34ch, 80%);
      min-width: 1ch;
      border: 0;
      border-bottom: 1px solid #007acc;
      background: transparent;
      color: #1e1e1e;
      font: inherit;
      outline: none;
      caret-color: #007acc;
      padding: 0 2px;
    }
    .terminal-input:focus {
      background: #eef6ff;
    }
    .empty {
      color: var(--muted);
      min-height: 100%;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 24px;
    }
    @media (max-width: 900px) {
      .topbar { align-items: flex-start; flex-direction: column; }
      .runtime-bar { justify-content: flex-start; width: 100%; }
      .runtime-status { text-align: left; }
      .workspace {
        grid-template-columns: 1fr;
        height: auto;
        min-height: calc(100vh - 100px);
      }
      .pane { min-height: 420px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark">Py</div>
      <div>
        <h1>便携 Python 教学运行台</h1>
      </div>
    </div>
    <div class="runtime-bar">
      <div class="runtime-tabs" role="group" aria-label="Python 版本">
        <button type="button" data-version="3.12">Python 3.12</button>
        <button type="button" data-version="3.7" class="active">Python 3.7</button>
      </div>
      <div id="runtimeStatus" class="runtime-status">Python 3.7</div>
    </div>
  </header>

  <main class="workspace">
    <section class="pane">
      <div class="pane-head">
        <div class="pane-title">代码</div>
        <div class="actions">
          <button id="clearBtn" type="button" class="secondary">清空</button>
          <button id="runBtn" type="button" class="command">运行</button>
        </div>
      </div>
      <div class="editor-wrap">
        <div id="gutter" class="gutter" aria-hidden="true">1</div>
        <textarea id="code" class="editor" spellcheck="false">import sys
import pandas as pd
import matplotlib.pyplot as plt

print(sys.version)
print("pandas", pd.__version__)

df = pd.read_excel("data.xlsx")
display(df.head())

plt.plot([1, 2, 3, 4], [1, 4, 9, 16], marker="o")
plt.title("Python version check")
plt.xlabel("x")
plt.ylabel("y")

a = int(input("请输入第一个整数："))
b = int(input("请输入第二个整数："))
print("两个整数的和是：", a + b)</textarea>
      </div>
    </section>

    <section class="pane">
      <div class="pane-head">
        <div class="pane-title">运行结果</div>
        <div id="runState" class="runtime-status">等待运行</div>
      </div>
      <div id="output" class="output">
        <div class="empty">输出会显示在这里</div>
      </div>
    </section>
  </main>

  <script>
    const codeEl = document.getElementById("code");
    const gutterEl = document.getElementById("gutter");
    const outputEl = document.getElementById("output");
    const runBtn = document.getElementById("runBtn");
    const clearBtn = document.getElementById("clearBtn");
    const runState = document.getElementById("runState");
    const runtimeStatus = document.getElementById("runtimeStatus");
    const versionButtons = Array.from(document.querySelectorAll("[data-version]"));
    const DRAFT_KEY = "pythonTeachingDraft";
    let currentVersion = "3.7";
    let interactiveSessionId = null;
    let pollTimer = null;
    let lastTerminalStdout = "";

    function updateGutter() {
      const lineCount = codeEl.value.split("\n").length || 1;
      let numbers = "";
      for (let i = 1; i <= lineCount; i += 1) {
        numbers += i + "\n";
      }
      gutterEl.textContent = numbers;
      gutterEl.scrollTop = codeEl.scrollTop;
    }

    function saveDraft() {
      try {
        localStorage.setItem(DRAFT_KEY, codeEl.value);
      } catch (error) {
        // Private mode or a full quota: losing autosave is not worth interrupting class.
      }
    }

    function restoreDraft() {
      try {
        const saved = localStorage.getItem(DRAFT_KEY);
        if (saved !== null) {
          codeEl.value = saved;
        }
      } catch (error) {
        // Ignore unreadable storage and keep the built-in sample code.
      }
    }

    function setVersion(version) {
      currentVersion = version;
      versionButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.version === version);
      });
      runtimeStatus.textContent = `Python ${version}`;
    }

    function stopPolling() {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    async function stopCurrentSession() {
      const sessionId = interactiveSessionId;
      interactiveSessionId = null;
      stopPolling();
      if (sessionId) {
        try {
          await fetch(`/run/interactive/stop/${encodeURIComponent(sessionId)}`, { method: "POST" });
        } catch (error) {
          // The page is being reset; a failed stop request does not need UI noise.
        }
      }
    }

    function appendPre(text, className = "") {
      if (!text) return;
      const pre = document.createElement("pre");
      pre.className = className;
      pre.textContent = text;
      outputEl.appendChild(pre);
    }

    function appendRuntimeOutputs(data) {
      for (const item of data.outputs || []) {
        if (item.type === "html") {
          const wrap = document.createElement("div");
          wrap.className = "runtime-html";
          wrap.innerHTML = item.html;
          outputEl.appendChild(wrap);
        }
        if (item.type === "image") {
          const fig = document.createElement("figure");
          const img = document.createElement("img");
          img.src = item.src;
          img.alt = "Python 生成图像";
          fig.appendChild(img);
          outputEl.appendChild(fig);
        }
        if (item.type === "text") {
          appendPre(item.text);
        }
      }
    }

    function renderStartup() {
      outputEl.replaceChildren();
      const terminal = document.createElement("div");
      terminal.className = "terminal";
      terminal.textContent = "正在启动 Python 进程...";
      outputEl.appendChild(terminal);
    }

    function renderInteractive(data) {
      const stdout = data.stdout || "";
      const requestId = String(data.input_request_id || "");
      const existingInput = outputEl.querySelector(".terminal-input");
      if (
        data.waiting_for_input &&
        existingInput &&
        existingInput.dataset.requestId === requestId &&
        lastTerminalStdout === stdout
      ) {
        return;
      }

      outputEl.replaceChildren();

      const terminal = document.createElement("div");
      terminal.className = "terminal";
      const text = document.createElement("span");
      text.textContent = stdout;
      terminal.appendChild(text);

      let inputToFocus = null;
      if (data.waiting_for_input && !data.completed) {
        inputToFocus = document.createElement("input");
        inputToFocus.className = "terminal-input";
        inputToFocus.dataset.requestId = requestId;
        inputToFocus.autocomplete = "off";
        inputToFocus.spellcheck = false;
        inputToFocus.setAttribute("aria-label", "输入后按回车");
        inputToFocus.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            submitInteractiveInput(inputToFocus.value);
          }
        });
        terminal.appendChild(inputToFocus);
      }

      outputEl.appendChild(terminal);

      if (data.completed) {
        appendRuntimeOutputs(data);
      }
      appendPre(data.stderr || "", "stderr");
      if (data.completed) {
        appendPre(data.ok ? `运行完成：Python ${data.version}` : `运行失败：Python ${data.version}`, data.ok ? "feedback" : "stderr");
      }

      if (!outputEl.children.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "程序已运行，没有文本输出";
        outputEl.appendChild(empty);
      }

      lastTerminalStdout = stdout;
      outputEl.scrollTop = outputEl.scrollHeight;
      if (inputToFocus) {
        setTimeout(() => inputToFocus.focus(), 0);
      }
    }

    async function pollInteractiveStatus() {
      const sessionId = interactiveSessionId;
      if (!sessionId) return;

      const response = await fetch(`/run/interactive/status/${encodeURIComponent(sessionId)}`);
      const data = await response.json();
      if (sessionId !== interactiveSessionId) return;

      renderInteractive(data);
      if (data.completed) {
        interactiveSessionId = null;
        stopPolling();
        runBtn.disabled = false;
        runState.textContent = data.ok ? "运行完成" : "运行失败";
      } else if (data.waiting_for_input) {
        runState.textContent = `等待输入：Python ${data.version}`;
      } else {
        runState.textContent = `运行中：Python ${data.version}`;
      }
    }

    async function submitInteractiveInput(value) {
      const sessionId = interactiveSessionId;
      if (!sessionId) return;

      const input = outputEl.querySelector(".terminal-input");
      if (input) {
        input.disabled = true;
      }

      try {
        await fetch(`/run/interactive/input/${encodeURIComponent(sessionId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: value })
        });
        await pollInteractiveStatus();
      } catch (error) {
        outputEl.replaceChildren();
        appendPre(`提交输入失败：${error.message}`, "stderr");
        runState.textContent = "连接失败";
        runBtn.disabled = false;
        stopPolling();
      }
    }

    async function runCode() {
      await stopCurrentSession();
      runBtn.disabled = true;
      runState.textContent = `运行中：Python ${currentVersion}`;
      lastTerminalStdout = "";
      renderStartup();

      try {
        const response = await fetch("/run/interactive/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            version: currentVersion,
            code: codeEl.value
          })
        });
        const data = await response.json();
        if (!data.ok) {
          outputEl.replaceChildren();
          appendPre(data.stderr || "无法启动 Python 进程。", "stderr");
          runState.textContent = "运行失败";
          runBtn.disabled = false;
          return;
        }

        interactiveSessionId = data.session_id;
        await pollInteractiveStatus();
        pollTimer = setInterval(() => {
          pollInteractiveStatus().catch((error) => {
            stopPolling();
            outputEl.replaceChildren();
            appendPre(`读取运行状态失败：${error.message}`, "stderr");
            runState.textContent = "连接失败";
            runBtn.disabled = false;
          });
        }, 250);
      } catch (error) {
        outputEl.replaceChildren();
        appendPre(`连接本地运行服务失败：${error.message}`, "stderr");
        runState.textContent = "连接失败";
        runBtn.disabled = false;
      }
    }

    versionButtons.forEach((button) => {
      button.addEventListener("click", () => setVersion(button.dataset.version));
    });
    runBtn.addEventListener("click", runCode);
    clearBtn.addEventListener("click", async () => {
      await stopCurrentSession();
      codeEl.value = "";
      saveDraft();
      updateGutter();
      outputEl.innerHTML = '<div class="empty">输出会显示在这里</div>';
      runState.textContent = "等待运行";
      runBtn.disabled = false;
    });
    codeEl.addEventListener("input", () => {
      updateGutter();
      saveDraft();
    });
    codeEl.addEventListener("scroll", () => {
      gutterEl.scrollTop = codeEl.scrollTop;
    });
    codeEl.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        runCode();
      }
      if (event.key === "Tab") {
        event.preventDefault();
        const start = codeEl.selectionStart;
        const end = codeEl.selectionEnd;
        codeEl.value = `${codeEl.value.slice(0, start)}    ${codeEl.value.slice(end)}`;
        codeEl.selectionStart = codeEl.selectionEnd = start + 4;
        updateGutter();
        saveDraft();
      }
    });

    restoreDraft();
    updateGutter();
    setVersion(currentVersion);
  </script>
</body>
</html>
"""


def clean_stderr(stderr: str | None) -> str:
    if not stderr:
        return ""
    ignored = {"Matplotlib is building the font cache; this may take a moment."}
    lines = [line for line in stderr.splitlines() if line.strip() not in ignored]
    return "\n".join(lines)


def safe_child_path(parent: Path, child: Path) -> Path:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    try:
        child_resolved.relative_to(parent_resolved)
    except ValueError as exc:
        raise FileNotFoundError("Path is outside the allowed directory.") from exc
    return child_resolved


def runtime_path(version: str) -> Path:
    return RUNTIMES[normalize_version(version)]


def runtime_compatibility_error(version: str) -> str:
    if version == "3.12" and sys.platform == "win32":
        windows_version = sys.getwindowsversion()
        if (windows_version.major, windows_version.minor) < (6, 3):
            return "这台电脑的 Windows 版本不支持 Python 3.12，请切换到 Python 3.7。"
    return ""


def normalize_version(version: str) -> str:
    return "3.7" if str(version).strip() in {"37", "3.7"} else "3.12"


def runner_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(MPL_CACHE)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONTEACHING_HOME"] = str(BASE_DIR)
    if extra:
        env.update(extra)
    return env


# Imports matplotlib + pandas and builds matplotlib's font cache once, so the
# slow one-time work happens in the background right after launch (while the
# teacher is still introducing the lesson) instead of stalling a student's
# first plot for minutes on an old PC.
WARMUP_CODE = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import matplotlib.pyplot as plt\n"
    "from matplotlib import font_manager\n"
    "import pandas\n"
    "fig = plt.figure()\n"
    "plt.plot([0, 1], [0, 1])\n"
    "import io\n"
    "fig.savefig(io.BytesIO(), format='png')\n"
)


def warmup_runtime(version: str) -> None:
    python_path = runtime_path(version)
    if not python_path.exists():
        return
    try:
        subprocess.run(
            [str(python_path), "-c", WARMUP_CODE],
            cwd=BASE_DIR,
            env=runner_environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIMEOUT_SECONDS * 6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        # Best-effort: if warmup fails or times out, the first real plot simply
        # pays the build cost as before; nothing breaks.
        pass


def warmup_runtimes(versions: tuple[str, ...] = ("3.7", "3.12")) -> None:
    for version in versions:
        if runtime_compatibility_error(version):
            continue
        warmup_runtime(version)


def warmup_runtimes_in_background() -> None:
    thread = threading.Thread(target=warmup_runtimes, daemon=True)
    thread.start()


def read_result_outputs(result_path: Path) -> list[dict]:
    if not result_path.exists():
        return []
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    outputs = result.get("outputs", [])
    return outputs if isinstance(outputs, list) else []


def stream_reader(session: dict, stream_name: str) -> None:
    stream = session["process"].stdout if stream_name == "stdout" else session["process"].stderr
    parts_key = f"{stream_name}_parts"
    try:
        while True:
            chunk = stream.read(1)
            if chunk == "":
                break
            with session["lock"]:
                session[parts_key].append(chunk)
                session["updated_at"] = time.time()
    except Exception:
        return


def interactive_state(session: dict) -> dict:
    state_path = session.get("state_path")
    if not state_path:
        return {"waiting": False, "prompt": "", "request_id": ""}
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"waiting": False, "prompt": "", "request_id": ""}
    return {
        "waiting": bool(state.get("waiting")),
        "prompt": str(state.get("prompt", "")),
        "request_id": str(state.get("request_id", "")),
    }


def finalize_session(session: dict) -> bool:
    process = session["process"]
    returncode = process.poll()
    if returncode is None:
        return False

    if not session.get("completed"):
        for thread_key in ("stdout_thread", "stderr_thread"):
            thread = session.get(thread_key)
            if thread:
                thread.join(timeout=0.2)
        with session["lock"]:
            session["returncode"] = returncode
            session["outputs"] = read_result_outputs(session["result_path"])
            session["completed"] = True
            session["updated_at"] = time.time()
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
    return True


def stop_process(session: dict, message: str = "") -> None:
    process = session["process"]
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=2)
            except OSError:
                pass
    if message:
        with session["lock"]:
            if session["stderr_parts"] and not "".join(session["stderr_parts"]).endswith("\n"):
                session["stderr_parts"].append("\n")
            session["stderr_parts"].append(message)
            session["updated_at"] = time.time()
    finalize_session(session)


def remove_output_dir(output_dir: Path | None) -> None:
    # Each run leaves a folder under run_outputs/ on the USB drive. Without this
    # the folder would never be deleted, so a drive used all semester would fill
    # up with thousands of small files and slow down.
    if not output_dir:
        return
    try:
        resolved = output_dir.resolve()
        resolved.relative_to(OUTPUT_ROOT.resolve())
    except (OSError, ValueError):
        return
    shutil.rmtree(resolved, ignore_errors=True)


def cleanup_sessions() -> None:
    now = time.time()
    with SESSIONS_LOCK:
        items = list(SESSIONS.items())

    for session_id, session in items:
        finalize_session(session)
        age = now - float(session.get("updated_at", session.get("started_at", now)))
        lifetime = now - float(session.get("started_at", now))
        if not session.get("completed") and lifetime > INTERACTIVE_SESSION_TTL:
            stop_process(session, "运行时间过长，已自动停止。")
        if session.get("completed") and age > 60:
            with SESSIONS_LOCK:
                SESSIONS.pop(session_id, None)
            remove_output_dir(session.get("output_dir"))


def purge_output_root() -> None:
    # On startup, clear any run folders left behind by an earlier session that
    # was closed abruptly (e.g. the USB drive was pulled or the PC lost power).
    if not OUTPUT_ROOT.exists():
        return
    for child in OUTPUT_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def session_payload(session: dict) -> dict:
    state = interactive_state(session)
    if not session.get("completed") and session["process"].poll() is None:
        last_resume_at = float(session.get("last_resume_at", session.get("started_at", time.time())))
        if not state["waiting"] and time.time() - last_resume_at > TIMEOUT_SECONDS:
            stop_process(session, f"运行超时：超过 {TIMEOUT_SECONDS} 秒，已停止执行。")

    finalize_session(session)
    completed = bool(session.get("completed"))
    with session["lock"]:
        stdout = "".join(session["stdout_parts"])
        stderr = "".join(session["stderr_parts"])
        outputs = list(session.get("outputs", []))
        returncode = session.get("returncode")

    return {
        "ok": completed and returncode == 0,
        "completed": completed,
        "returncode": returncode,
        "version": session["version"],
        "stdout": stdout,
        "stderr": clean_stderr(stderr),
        "outputs": outputs,
        "waiting_for_input": bool(state["waiting"]) and not completed,
        "input_prompt": state["prompt"],
        "input_request_id": state["request_id"],
    }


def start_interactive_run(version: str, code: str) -> dict:
    cleanup_sessions()
    normalized = normalize_version(version)
    python_path = runtime_path(normalized)
    compatibility_error = runtime_compatibility_error(normalized)
    if compatibility_error:
        return {"ok": False, "version": normalized, "stderr": compatibility_error}
    if not python_path.exists():
        return {
            "ok": False,
            "version": normalized,
            "stderr": f"Python {normalized} runtime was not found: {python_path}",
        }
    if not RUNNER.exists():
        return {"ok": False, "version": normalized, "stderr": f"runner.py was not found: {RUNNER}"}

    OUTPUT_ROOT.mkdir(exist_ok=True)
    MPL_CACHE.mkdir(exist_ok=True)
    run_id = uuid.uuid4().hex
    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    code_path = output_dir / "lesson_code.py"
    result_path = output_dir / "result.json"
    state_path = output_dir / "interactive_state.json"
    code_path.write_text(code, encoding="utf-8")
    state_path.write_text(
        json.dumps({"waiting": False, "prompt": "", "request_id": "", "updated_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )

    try:
        process = subprocess.Popen(
            [str(python_path), str(RUNNER), str(code_path), str(output_dir), str(result_path)],
            cwd=BASE_DIR,
            env=runner_environment(
                {
                    "PYTHONTEACHING_INTERACTIVE_STATE": str(state_path),
                    "PYTHONTEACHING_ECHO_INPUT": "1",
                }
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return {"ok": False, "version": normalized, "stderr": str(exc)}

    now = time.time()
    session = {
        "id": run_id,
        "version": normalized,
        "process": process,
        "output_dir": output_dir,
        "result_path": result_path,
        "state_path": state_path,
        "stdout_parts": [],
        "stderr_parts": [],
        "outputs": [],
        "returncode": None,
        "completed": False,
        "started_at": now,
        "updated_at": now,
        "last_resume_at": now,
        "lock": threading.Lock(),
        "input_lock": threading.Lock(),
    }
    session["stdout_thread"] = threading.Thread(target=stream_reader, args=(session, "stdout"), daemon=True)
    session["stderr_thread"] = threading.Thread(target=stream_reader, args=(session, "stderr"), daemon=True)
    session["stdout_thread"].start()
    session["stderr_thread"].start()

    with SESSIONS_LOCK:
        SESSIONS[run_id] = session

    return {"ok": True, "session_id": run_id, "version": normalized}


def get_session(session_id: str) -> dict | None:
    with SESSIONS_LOCK:
        return SESSIONS.get(session_id)


def submit_interactive_input(session_id: str, text: str) -> tuple[int, dict]:
    session = get_session(session_id)
    if not session:
        return 404, {"ok": False, "completed": True, "stderr": "运行会话不存在或已经结束。", "outputs": []}

    process = session["process"]
    if process.poll() is not None:
        finalize_session(session)
        return 200, session_payload(session)

    one_line = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    try:
        with session["input_lock"]:
            if process.stdin is None:
                raise BrokenPipeError("stdin is closed")
            process.stdin.write(one_line + "\n")
            process.stdin.flush()
            session["last_resume_at"] = time.time()
            session["updated_at"] = time.time()
    except (BrokenPipeError, OSError) as exc:
        with session["lock"]:
            session["stderr_parts"].append(f"输入提交失败：{exc}")
        finalize_session(session)

    return 200, session_payload(session)


def run_user_code(version: str, code: str, stdin_text: str = "") -> dict:
    normalized = normalize_version(version)
    python_path = runtime_path(normalized)
    compatibility_error = runtime_compatibility_error(normalized)
    if compatibility_error:
        return {
            "ok": False,
            "version": normalized,
            "stdout": "",
            "stderr": compatibility_error,
            "outputs": [],
        }
    if not python_path.exists():
        return {
            "ok": False,
            "version": normalized,
            "stdout": "",
            "stderr": f"Python {normalized} runtime was not found: {python_path}",
            "outputs": [],
        }
    if not RUNNER.exists():
        return {
            "ok": False,
            "version": normalized,
            "stdout": "",
            "stderr": f"runner.py was not found: {RUNNER}",
            "outputs": [],
        }

    run_id = uuid.uuid4().hex
    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    code_path = output_dir / "lesson_code.py"
    result_path = output_dir / "result.json"
    code_path.write_text(code, encoding="utf-8")

    if stdin_text and not stdin_text.endswith("\n"):
        stdin_text += "\n"

    try:
        completed = subprocess.run(
            [str(python_path), str(RUNNER), str(code_path), str(output_dir), str(result_path)],
            cwd=BASE_DIR,
            env=runner_environment(),
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "version": normalized,
            "stdout": exc.stdout or "",
            "stderr": f"运行超时：超过 {TIMEOUT_SECONDS} 秒，已停止执行。",
            "outputs": [],
        }

    result = {"outputs": []}
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {"outputs": []}

    return {
        "ok": completed.returncode == 0,
        "version": normalized,
        "stdout": completed.stdout,
        "stderr": clean_stderr(completed.stderr),
        "outputs": result.get("outputs", []),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PortablePythonTeaching/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict) -> None:
        self.send_bytes(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            self.send_bytes(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path.startswith("/run/interactive/status/"):
            session_id = unquote(path.rsplit("/", 1)[-1])
            session = get_session(session_id)
            if not session:
                self.send_json(404, {"ok": False, "completed": True, "stderr": "运行会话不存在或已经结束。", "outputs": []})
                return
            self.send_json(200, session_payload(session))
            return
        if path.startswith("/run_outputs/"):
            relative = unquote(path[len("/run_outputs/") :])
            try:
                file_path = safe_child_path(OUTPUT_ROOT, OUTPUT_ROOT / relative)
            except FileNotFoundError:
                self.send_error(404)
                return
            if not file_path.is_file():
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            self.send_bytes(200, file_path.read_bytes(), content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"ok": False, "stderr": "请求数据不是有效 JSON。", "outputs": []})
            return

        path = parsed.path
        if path == "/run/interactive/start":
            self.send_json(200, start_interactive_run(str(payload.get("version", "3.12")), str(payload.get("code", ""))))
            return

        if path.startswith("/run/interactive/input/"):
            session_id = unquote(path.rsplit("/", 1)[-1])
            status, result = submit_interactive_input(session_id, str(payload.get("text", "")))
            self.send_json(status, result)
            return

        if path.startswith("/run/interactive/stop/"):
            session_id = unquote(path.rsplit("/", 1)[-1])
            session = get_session(session_id)
            if not session:
                self.send_json(200, {"ok": True, "completed": True, "outputs": []})
                return
            stop_process(session, "运行已停止。")
            self.send_json(200, session_payload(session))
            return

        if path == "/run":
            result = run_user_code(
                str(payload.get("version", "3.12")),
                str(payload.get("code", "")),
                str(payload.get("stdin", payload.get("input", ""))),
            )
            self.send_json(200, result)
            return

        self.send_error(404)


def available_port(host: str, preferred: int) -> int:
    candidates = [preferred, 5000, 5001, 8765, 8766]
    for port in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((host, port))
            return port
        except OSError:
            continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def self_test() -> int:
    code = "import sys, pandas as pd\nprint(sys.version.split()[0])\nprint(pd.__version__)"
    ok = True
    for version in ("3.7", "3.12"):
        result = run_user_code(version, code)
        print(f"Python {version}:", "OK" if result["ok"] else "FAILED")
        print(result["stdout"].strip())
        if result["stderr"]:
            print(result["stderr"], file=sys.stderr)
        ok = ok and bool(result["ok"])
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("PYTHONTEACHING_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PYTHONTEACHING_PORT", "8765")))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--warmup", action="store_true",
                        help="预先构建字体缓存后退出（制作 U 盘时跑一次，让课堂首图更快）")
    parser.add_argument("--no-warmup", action="store_true",
                        help="启动时不在后台预热运行时")
    args = parser.parse_args(argv)

    OUTPUT_ROOT.mkdir(exist_ok=True)
    MPL_CACHE.mkdir(exist_ok=True)
    purge_output_root()

    if args.self_test:
        return self_test()

    if args.warmup:
        print("Warming up runtimes (building matplotlib font cache)...", flush=True)
        warmup_runtimes()
        print("Warmup done.", flush=True)
        return 0

    port = available_port(args.host, args.port)
    httpd = PortableThreadingHTTPServer((args.host, port), Handler)
    port = int(httpd.server_address[1])
    url = f"http://{'127.0.0.1' if args.host in {'0.0.0.0', '::'} else args.host}:{port}/"
    print(f"Portable Python teaching shell: {url}", flush=True)
    print("Keep this window open while using the webpage.", flush=True)

    if not args.no_browser:
        timer = threading.Timer(0.8, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()

    if not args.no_warmup:
        # Front-load matplotlib's one-time font-cache build in the background so
        # the first plot of the lesson is fast instead of stalling for minutes.
        warmup_runtimes_in_background()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
