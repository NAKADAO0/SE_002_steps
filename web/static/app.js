/* All model/user text is rendered through textContent, never interpreted as HTML. */
const $ = (id) => document.getElementById(id);
const labels = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  failed: "执行失败",
  needs_attention: "待人工处理",
};
const roles = {
  code: ["编码 Agent", "生成并交接初始代码", "⌘"],
  review: ["审查 Agent", "结合模型与静态规则检查代码", "◎"],
  fix: ["修复 Agent", "根据审查意见修复当前版本", "↗"],
};
let current = null,
  selectedId = null,
  selectedTab = "code",
  pollTimer = null,
  busy = false,
  settings = {};
let requestSequence = 0,
  pollFailures = 0;
let sourceFilename = "",
  uploading = false,
  attachmentSequence = 0;
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const icon = (name) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"),
    use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
};
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json();
  if (!response.ok) {
    let detail = data.detail;
    if (Array.isArray(detail)) detail = detail.map((x) => x.msg).join("；");
    throw new Error(detail || `请求失败 ${response.status}`);
  }
  return data;
}
function showError(message) {
  $("error-banner").textContent = message;
  $("error-banner").hidden = !message;
}
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  setTimeout(() => ($("toast").hidden = true), 2300);
}
function setBusy(value) {
  busy = value;
  $("send-task").disabled = value || uploading;
  $("upload-file").disabled = value || uploading || $("mode").value === "demo";
  $("source-code").disabled = uploading || $("mode").value === "demo";
  $("send-task").setAttribute("aria-label", value ? "任务执行中" : "启动任务");
}
function setMode() {
  const demo = $("mode").value === "demo";
  $("mode-note").textContent = demo
    ? "固定平均值演示 · 不调用真实模型"
    : "源码仅做静态检查，不自动执行。";
  $("statusbar-mode").textContent = demo
    ? "离线演示"
    : settings.model || "DeepSeek";
  $("requirement").disabled = demo;
  $("source-code").disabled = demo || uploading;
  $("upload-file").disabled = demo || uploading || busy;
}
function newTask() {
  clearTimeout(pollTimer);
  requestSequence++;
  current = null;
  selectedId = null;
  setBusy(false);
  showError("");
  $("welcome").hidden = false;
  $("task-content").hidden = true;
  $("task-title").textContent = "新建任务";
  $("requirement").value = "";
  $("source-code").value = "";
  clearAttachment();
  $("source-wrap").hidden = true;
  $("resume-run").hidden = true;
  $("sidebar").classList.remove("visible");
  renderArtifact();
  refreshHistory();
  $("requirement").focus();
}
async function refreshHistory() {
  try {
    const runs = await api("/api/runs");
    const container = $("history");
    container.replaceChildren();
    if (!runs.length) {
      container.append(
        el("div", "history-empty", "还没有任务\n从一个代码需求开始。"),
      );
      return;
    }
    for (const run of runs) {
      const button = el(
        "button",
        "history-item" + (run.run_id === selectedId ? " active" : ""),
      );
      button.append(icon("clock"));
      const details = el("div");
      details.append(el("div", "history-title", run.requirement));
      const meta = el("div", "history-meta");
      meta.append(
        el("span", "tiny-dot"),
        el("span", "", labels[run.status] || run.status),
        el("span", "", run.mode === "demo" ? "演示" : "DeepSeek"),
      );
      details.append(meta);
      button.append(details);
      button.title = run.requirement;
      button.onclick = () => selectRun(run.run_id);
      container.append(button);
    }
  } catch (error) {
    $("connection-text").textContent = "服务连接异常";
  }
}
async function selectRun(id) {
  clearTimeout(pollTimer);
  selectedId = id;
  const sequence = ++requestSequence;
  $("sidebar").classList.remove("visible");
  showError("");
  try {
    const state = await api(`/api/runs/${id}`);
    if (sequence !== requestSequence) return;
    current = state;
    pollFailures = 0;
    renderRun();
    refreshHistory();
    if (["pending", "running"].includes(state.status))
      pollTimer = setTimeout(() => selectRun(id), 1200);
  } catch (error) {
    if (sequence === requestSequence) {
      pollFailures++;
      showError(error.message + " · 正在重试连接…");
      setBusy(
        current?.run_id === id &&
          ["pending", "running"].includes(current.status),
      );
      pollTimer = setTimeout(
        () => selectRun(id),
        Math.min(10000, 1200 * 2 ** Math.min(pollFailures, 3)),
      );
    }
  }
}
function renderRun() {
  const state = current;
  if (!state) return;
  $("welcome").hidden = true;
  $("task-content").hidden = false;
  $("task-title").textContent = state.requirement;
  $("run-heading").textContent =
    state.requirement.length > 80
      ? state.requirement.slice(0, 80) + "…"
      : state.requirement;
  $("user-message").textContent =
    state.requirement +
    (state.source_filename ? `\n附件：${state.source_filename}` : "");
  $("run-status").textContent = labels[state.status] || state.status;
  $("run-status").className = "status-badge " + state.status;
  $("mode").value = state.mode;
  setMode();
  setBusy(["pending", "running"].includes(state.status));
  $("resume-run").hidden = state.status !== "failed";
  const timeline = $("agent-timeline");
  timeline.replaceChildren();
  const stages = [];
  for (const event of state.events) {
    if (event.kind === "node_started")
      stages.push({
        node: event.node,
        start: event.timestamp,
        status: "working",
        tools: [],
      });
    else if (stages.length) {
      const stage = stages[stages.length - 1];
      if (event.kind === "node_completed") {
        stage.status = "complete";
        stage.end = event.timestamp;
      } else if (
        event.kind === "node_failed" ||
        event.kind === "storage_or_worker_error"
      )
        stage.status = "error";
      else if (event.kind === "agent_call_tool")
        stage.tools.push(event.message);
    }
  }
  stages.forEach((stage, index) => {
    const role = roles[stage.node] || [stage.node, "处理任务", "·"];
    const card = el("div", "agent-card " + stage.status);
    const mark = el(
      "div",
      "agent-icon",
      stage.status === "complete" ? "✓" : role[2],
    );
    const info = el("div", "agent-info");
    const title = el("div", "agent-title");
    let name = role[0];
    if (
      stage.node === "review" &&
      stages.slice(0, index).some((x) => x.node === "review")
    )
      name = "审查 Agent · 复审";
    title.append(
      el("strong", "", name),
      el(
        "span",
        "",
        stage.status === "complete"
          ? "已完成"
          : stage.status === "error"
            ? "失败"
            : "正在处理…",
      ),
    );
    info.append(title, el("div", "agent-description", stage.node === "code" && state.source_code ? "读取并原样交接初始源码" : role[1]));
    const duration = stage.end
      ? `${Math.max(0, (new Date(stage.end) - new Date(stage.start)) / 1000).toFixed(1)}s`
      : "";
    info.append(
      el(
        "div",
        "agent-detail",
        [duration, ...stage.tools.map((x) => "tool: " + x)]
          .filter(Boolean)
          .join(" · "),
      ),
    );
    card.append(mark, info);
    timeline.append(card);
  });
  const result = $("result-message");
  result.replaceChildren();
  if (state.status === "completed") {
    result.append(
      el("div", "", state.intent === "review_only" ? "只审查流程已完成，原始代码未被修改。" : "审查与修复流程已完成。"),
      el("div", "", state.summary),
      el(
        "small",
        "",
        `修复 ${state.repairs} 次 · ${state.revisions.length} 个代码版本 · 当前审查无剩余问题。未执行生成代码测试。`,
      ),
    );
  } else if (state.status === "failed")
    result.append(
      el("div", "", state.error),
      el(
        "small",
        "",
        `可从 ${state.next_node} 节点恢复，保留已完成的代码版本。`,
      ),
    );
  else if (state.status === "needs_attention")
    result.append(
      el("div", "", state.intent === "review_only" ? "只审查流程已结束，发现问题；原始代码未被修改，请查看右侧审查意见。" : "流程达到上限，请查看右侧剩余问题并人工处理。"),
      el("small", "", state.summary),
    );
  else
    result.append(el("div", "", "Agent 正在协作，结果与代码版本将持续更新。"));
  renderArtifact();
}
function highlighted(line) {
  const fragment = document.createDocumentFragment();
  const regex =
    /(#[^\n]*|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\b(?:def|return|if|else|elif|for|in|while|import|from|class|raise|try|except|with|as|not|and|or|None|True|False|pass|lambda|yield)\b|\b\d+(?:\.\d+)?\b)/g;
  let offset = 0;
  for (const match of line.matchAll(regex)) {
    fragment.append(document.createTextNode(line.slice(offset, match.index)));
    const value = match[0];
    fragment.append(
      el(
        "span",
        value.startsWith("#")
          ? "token-comment"
          : value.startsWith('"') || value.startsWith("'")
            ? "token-string"
            : /^\d/.test(value)
              ? "token-number"
              : "token-keyword",
        value,
      ),
    );
    offset = match.index + value.length;
  }
  fragment.append(document.createTextNode(line.slice(offset)));
  return fragment;
}
function renderArtifact() {
  const container = $("artifact-content");
  $("issues-count").textContent = current?.issues?.length || "";
  const diff = current?.diff || "";
  $("diff-count").textContent = diff ? "1" : "";
  $("copy-code").disabled = !current?.code;
  $("download-code").disabled =
    !current?.code || current.status !== "completed";
  $("download-state").disabled = !current;
  const names = {
    code: current?.source_filename || "final_code.py",
    diff: "initial.py → current.py",
    issues: "review issues",
    logs: "events.jsonl",
  };
  $("artifact-label").replaceChildren(
    icon(selectedTab === "code" ? "code" : "clock"),
    document.createTextNode(names[selectedTab]),
  );
  container.replaceChildren();
  if (!current) {
    const empty = el("div", "artifact-empty");
    empty.append(
      icon("code"),
      el("h3", "", "代码将在这里呈现"),
      el("p", "", "跟随每个 Agent 的工作，\n查看代码、修改和审查结果。"),
    );
    const sample = el("div", "empty-code");
    sample.append(
      el("span", "", "01"),
      el("i", "", "# your next idea"),
      el("br"),
      el("span", "", "02"),
      el("i", "", "# starts here."),
    );
    empty.append(sample);
    container.append(empty);
    return;
  }
  if (selectedTab === "code") {
    if (!current.code) {
      container.append(el("div", "tab-empty", "编码 Agent 正在准备初始版本…"));
      return;
    }
    const view = el("div", "code-view");
    current.code.split("\n").forEach((line, index) => {
      const row = el("div", "code-line");
      row.append(el("span", "line-number", String(index + 1).padStart(2, "0")));
      const content = el("span", "line-content");
      content.append(highlighted(line));
      row.append(content);
      view.append(row);
    });
    container.append(view);
  } else if (selectedTab === "diff") {
    if (!diff)
      container.append(
        el(
          "div",
          "tab-empty",
          "当前版本与初始版本没有差异。\n修复后将在这里显示修改。",
        ),
      );
    else
      diff
        .split("\n")
        .forEach((line) =>
          container.append(
            el(
              "div",
              "diff-line " +
                (line.startsWith("+++") ||
                line.startsWith("---") ||
                line.startsWith("@@")
                  ? "meta"
                  : line.startsWith("+")
                    ? "addition"
                    : line.startsWith("-")
                      ? "deletion"
                      : ""),
              line,
            ),
          ),
        );
  } else if (selectedTab === "issues") {
    if (!current.issues.length) {
      container.append(
        el(
          "div",
          "tab-empty",
          current.status === "completed"
            ? "✓ 当前审查没有剩余问题"
            : "等待审查结果…",
        ),
      );
      return;
    }
    const list = el("div", "issue-list");
    current.issues.forEach((issue) => {
      const card = el("article", "issue"),
        head = el("div", "issue-head");
      head.append(
        el("span", "severity " + issue.severity, issue.severity),
        el("strong", "", issue.category),
      );
      card.append(
        head,
        el("p", "", `第 ${issue.line ?? "—"} 行 · ${issue.description}`),
        el("div", "issue-suggestion", issue.suggestion),
      );
      list.append(card);
    });
    container.append(list);
  } else {
    const list = el("div", "log-list");
    current.events.forEach((event) => {
      const row = el("div", "log-row");
      row.append(
        el(
          "time",
          "",
          new Date(event.timestamp).toLocaleTimeString("zh-CN", {
            hour12: false,
          }),
        ),
      );
      const content = el("div", "", `${event.node} / ${event.kind}`);
      if (event.message) content.append(el("small", "", event.message));
      row.append(content);
      list.append(row);
    });
    container.append(list);
  }
}
function download(content, filename, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = el("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("composer").onsubmit = async (event) => {
  event.preventDefault();
  if (busy || uploading) return;
  showError("");
  const submittedSequence = requestSequence;
  const mode = $("mode").value,
    requirement = $("requirement").value.trim();
  if (mode === "live" && !requirement && !$("source-code").value.trim()) {
    showError("描述你的代码需求，或先上传一个 Python 文件。");
    $("requirement").focus();
    return;
  }
  if (mode === "live" && !settings.configured) {
    showError(
      "DeepSeek 尚未配置，请在服务器 .env 中设置 API Key 并重启服务，或选择离线演示。",
    );
    return;
  }
  setBusy(true);
  try {
    const response = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        mode,
        requirement,
        source_code: $("source-code").value,
        source_filename: sourceFilename,
        max_repairs: Number($("max-repairs").value),
      }),
    });
    if (submittedSequence === requestSequence) {
      $("requirement").value = "";
      $("source-code").value = "";
      clearAttachment();
      $("source-wrap").hidden = true;
      await selectRun(response.run_id);
    } else refreshHistory();
  } catch (error) {
    if (submittedSequence === requestSequence) {
      showError(error.message);
      setBusy(false);
    }
  }
};
$("resume-run").onclick = async () => {
  if (!selectedId) return;
  const resumedSequence = requestSequence,
    resumedId = selectedId;
  showError("");
  $("resume-run").disabled = true;
  try {
    await api(`/api/runs/${resumedId}/resume`, { method: "POST" });
    if (resumedSequence === requestSequence) await selectRun(resumedId);
    else refreshHistory();
  } catch (error) {
    showError(error.message);
  } finally {
    $("resume-run").disabled = false;
  }
};
$("new-task").onclick = newTask;
$("refresh-history").onclick = refreshHistory;
$("attach-code").onclick = () => {
  $("source-wrap").hidden = !$("source-wrap").hidden;
  if (!$("source-wrap").hidden) $("source-code").focus();
};
$("clear-source").onclick = () => {
  clearAttachment();
  $("source-code").value = "";
  $("source-wrap").hidden = true;
};
function clearAttachment() {
  attachmentSequence++;
  uploading = false;
  sourceFilename = "";
  $("file-input").value = "";
  $("uploaded-file").hidden = true;
  $("uploaded-name").textContent = "";
  setBusy(busy);
}
$("mode").onchange = () => {
  if ($("mode").value === "demo") {
    clearAttachment();
    $("source-code").value = "";
    $("source-wrap").hidden = true;
  }
  setMode();
};
$("upload-file").onclick = () => $("file-input").click();
$("remove-file").onclick = () => {
  clearAttachment();
  $("source-code").value = "";
  $("source-wrap").hidden = true;
};
$("file-input").onchange = async (event) => {
  const file = event.target.files?.[0];
  if (!file || busy || $("mode").value === "demo") return;
  const sequence = ++attachmentSequence,
    pageSequence = requestSequence;
  showError("");
  if (!file.name.toLowerCase().endsWith(".py") || file.size > 100000) {
    showError("请上传不超过 100KB 的 .py 文件。");
    $("file-input").value = "";
    return;
  }
  uploading = true;
  setBusy(busy);
  try {
    const uploaded = await api(
      `/api/files?filename=${encodeURIComponent(file.name)}`,
      {
        method: "POST",
        body: file,
        headers: { "Content-Type": "application/octet-stream" },
      },
    );
    if (sequence !== attachmentSequence || pageSequence !== requestSequence)
      return;
    sourceFilename = uploaded.filename;
    $("source-code").value = uploaded.source_code;
    $("uploaded-name").textContent = uploaded.filename;
    $("uploaded-file").hidden = false;
    $("source-wrap").hidden = false;
    toast(`已读取 ${uploaded.filename}`);
  } catch (error) {
    if (sequence === attachmentSequence && pageSequence === requestSequence)
      showError(error.message);
  } finally {
    if (sequence === attachmentSequence) {
      uploading = false;
      setBusy(busy);
    }
  }
};
document.querySelectorAll("[data-example]").forEach(
  (button) =>
    (button.onclick = () => {
      clearAttachment();
      const kind = button.dataset.example;
      $("mode").value = kind === "demo" ? "demo" : "live";
      $("requirement").value =
        kind === "generate"
          ? "实现一个稳定去重函数 unique(values)，保留元素首次出现的顺序，空列表返回空列表。"
          : "实现 average(values)，接受数值列表，非空返回平均值，空列表返回 0.0。";
      $("source-code").value =
        kind === "generate"
          ? ""
          : "def average(values):\n    return sum(values) / len(values)\n";
      $("source-wrap").hidden = kind === "generate" || kind === "demo";
      setMode();
      $("requirement").focus();
    }),
);
document.querySelectorAll("[data-tab]").forEach(
  (button) =>
    (button.onclick = () => {
      selectedTab = button.dataset.tab;
      document
        .querySelectorAll("[data-tab]")
        .forEach((item) =>
          item.setAttribute("aria-selected", String(item === button)),
        );
      renderArtifact();
    }),
);
$("copy-code").onclick = async () => {
  try {
    await navigator.clipboard.writeText(current.code);
    toast("代码已复制");
  } catch {
    toast("浏览器未允许剪贴板访问，可下载代码。");
  }
};
$("download-code").onclick = () => {
  if (!current?.code || current.status !== "completed") return;
  const state = current;
  const link = el("a");
  link.href = `/api/runs/${state.run_id}/export`;
  link.download = state.source_filename || "final_code.py";
  document.body.append(link);
  link.click();
  link.remove();
  toast("已请求导出最终代码");
};
$("download-state").onclick = () => {
  if (current)
    download(
      JSON.stringify(current, null, 2),
      "state.json",
      "application/json",
    );
};
$("theme-toggle").onclick = () => {
  document.body.classList.toggle("dark");
  localStorage.setItem(
    "review-theme",
    document.body.classList.contains("dark") ? "dark" : "light",
  );
};
if (localStorage.getItem("review-theme") === "dark")
  document.body.classList.add("dark");
$("toggle-inspector").onclick = () => {
  if (innerWidth <= 960) document.body.classList.toggle("mobile-inspector");
  else document.body.classList.toggle("hide-inspector");
};
$("sidebar-open").onclick = () => $("sidebar").classList.add("visible");
$("sidebar-close").onclick = () => $("sidebar").classList.remove("visible");
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    $("composer").requestSubmit();
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
    event.preventDefault();
    newTask();
  }
});
async function init() {
  try {
    settings = await api("/api/settings");
    $("connection-text").textContent = settings.configured
      ? "DeepSeek 已连接配置"
      : "尚未配置模型";
    $("connection-dot").parentElement.classList.toggle(
      "unconfigured",
      !settings.configured,
    );
    if (!settings.configured) $("mode").value = "demo";
    setMode();
    renderArtifact();
    await refreshHistory();
  } catch (error) {
    showError("无法连接服务器，请刷新页面。");
  }
}
init();
