// Run: node --test docs/frontend-regression.cjs
// Executes the actual browser script with a small DOM and controlled fetch/timers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const appSource = fs.readFileSync(
  path.join(__dirname, "../web/static/app.js"),
  "utf8",
);

function node() {
  const classes = new Set();
  return {
    value: "",
    textContent: "",
    hidden: false,
    disabled: false,
    children: [],
    namespaceURI: "http://www.w3.org/2000/svg",
    classList: {
      add: (value) => classes.add(value),
      remove: (value) => classes.delete(value),
      contains: (value) => classes.has(value),
      toggle(value) {
        if (classes.has(value)) classes.delete(value);
        else classes.add(value);
      },
    },
    append(...children) {
      this.children.push(...children);
    },
    replaceChildren(...children) {
      this.children = children;
    },
    setAttribute(name, value) {
      this[name] = value;
    },
    focus() {},
  };
}

function harness(fetchHandler) {
  const elements = new Map(),
    timers = new Map(),
    requests = [];
  let nextTimer = 0;
  const get = (id) => {
    if (!elements.has(id)) {
      const element = node();
      element.parentElement = node();
      elements.set(id, element);
    }
    return elements.get(id);
  };
  const context = vm.createContext({
    console,
    document: {
      getElementById: get,
      createElement: node,
      createElementNS: node,
      createDocumentFragment: node,
      createTextNode: (text) => ({ textContent: text }),
      querySelectorAll: () => [],
      addEventListener() {},
      body: node(),
    },
    localStorage: { getItem: () => null, setItem() {} },
    setTimeout(callback, delay) {
      const id = ++nextTimer;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    fetch: async (url, options = {}) => {
      requests.push({ url, method: options.method || "GET" });
      const data = await fetchHandler(url, options);
      return { ok: true, json: async () => data };
    },
  });
  // Initialization has its own settings request; omit only its final invocation.
  vm.runInContext(appSource.replace(/init\(\);\s*$/, ""), context, {
    filename: "app.js",
  });
  get("mode").value = "demo";
  get("max-repairs").value = "2";
  const evaluate = (code) => vm.runInContext(code, context);
  return {
    get,
    evaluate,
    timers,
    requests,
    async fireTimer() {
      const next = timers.entries().next().value;
      assert.ok(next, "a retry/poll timer must be scheduled");
      timers.delete(next[0]);
      await next[1].callback();
      return next[1].delay;
    },
  };
}

function state(status, runId = "run-a") {
  return {
    run_id: runId,
    requirement: "review this code",
    mode: "demo",
    status,
    events: [],
    revisions: [],
    issues: [],
    code: "",
    diff: "",
    summary: "",
    repairs: 0,
  };
}

test("uploaded code can trigger workflow without a separate requirement", async () => {
  let submitted;
  const h = harness((url, options) => {
    if (url.startsWith("/api/files?")) return {filename:"average.py",source_code:"x = 1\n"};
    if (url === "/api/runs" && options.method === "POST") {
      submitted = JSON.parse(options.body);
      return {run_id:"uploaded-run"};
    }
    if (url === "/api/runs/uploaded-run") return state("completed","uploaded-run");
    if (url === "/api/runs") return [];
    throw new Error(url);
  });
  h.evaluate('settings = {configured:true}; $("mode").value = "live";');
  await h.evaluate('$("file-input").onchange({target:{files:[{name:"average.py",size:20}]}})');
  assert.equal(h.get("source-code").value,"x = 1\n");
  assert.equal(h.get("uploaded-file").hidden,false);
  await h.evaluate('$("composer").onsubmit({preventDefault(){}})');
  assert.equal(submitted.source_filename,"average.py");
  assert.equal(submitted.source_code,"x = 1\n");
  assert.equal(submitted.requirement,"");
});

test("delayed upload does not populate a newly opened task", async () => {
  let finishUpload;
  const h = harness(url => {
    if (url.startsWith("/api/files?")) return new Promise(resolve => finishUpload=resolve);
    if (url === "/api/runs") return [];
    throw new Error(url);
  });
  h.evaluate('$("mode").value = "live";');
  const pending=h.evaluate('$("file-input").onchange({target:{files:[{name:"old.py",size:20}]}})');
  h.evaluate('newTask()');
  finishUpload({filename:"old.py",source_code:"x=1"});
  await pending;
  assert.equal(h.get("source-code").value,"");
  assert.equal(h.evaluate('sourceFilename'),"");
  assert.equal(h.evaluate('uploading'),false);
});

test("final code export stays disabled until review is completed", () => {
  const h=harness(() => []);
  const snapshot={...state("failed"),code:"x=1\n"};
  h.evaluate(`current = ${JSON.stringify(snapshot)}; renderArtifact()`);
  assert.equal(h.get("download-code").disabled,true);
  h.evaluate('current.status="completed"; renderArtifact()');
  assert.equal(h.get("download-code").disabled,false);
});

test("a transient polling failure preserves busy state and retries to completion", async () => {
  let detailRequests = 0;
  const h = harness((url) => {
    if (url === "/api/runs") return [];
    assert.equal(url, "/api/runs/run-a");
    detailRequests++;
    if (detailRequests === 2) throw new Error("temporary network failure");
    return state(detailRequests === 1 ? "running" : "completed");
  });
  await h.evaluate('selectRun("run-a")');
  assert.equal(h.get("send-task").disabled, true);
  await h.fireTimer();
  assert.equal(h.evaluate("current.status"), "running");
  assert.equal(
    h.get("send-task").disabled,
    true,
    "a failed poll must not unlock an executing task",
  );
  assert.equal(h.timers.size, 1, "a failed poll must schedule a retry");
  const retryDelay = await h.fireTimer();
  assert.ok(
    retryDelay > 0 && retryDelay <= 10000,
    "retry uses a bounded delay",
  );
  assert.equal(detailRequests, 3);
  assert.equal(h.evaluate("current.status"), "completed");
  assert.equal(h.get("send-task").disabled, false);
  assert.equal(h.timers.size, 0, "completed tasks stop polling");
});

test("a delayed submission cannot replace a new task page", async () => {
  let resolvePost;
  const h = harness((url, options) => {
    if (url === "/api/runs" && options.method === "POST") {
      return new Promise((resolve) => {
        resolvePost = resolve;
      });
    }
    if (url === "/api/runs") return [];
    return state("completed", "submitted-run");
  });
  const submission = h.get("composer").onsubmit({ preventDefault() {} });
  assert.equal(
    typeof resolvePost,
    "function",
    "submission must be pending at the server",
  );
  h.evaluate("newTask()");
  assert.equal(h.evaluate("selectedId"), null);
  resolvePost({ run_id: "submitted-run" });
  await submission;
  assert.equal(
    h.evaluate("selectedId"),
    null,
    "the old POST must not select its task after navigation",
  );
  assert.equal(h.evaluate("current"), null);
  assert.equal(h.get("task-title").textContent, "新建任务");
  assert.equal(h.get("welcome").hidden, false);
  assert.equal(h.get("send-task").disabled, false);
  assert.equal(
    h.requests.filter((request) => request.url === "/api/runs/submitted-run")
      .length,
    0,
  );
});

test("submission without navigation still opens the created task", async () => {
  const h = harness((url, options) => {
    if (url === "/api/runs" && options.method === "POST")
      return { run_id: "submitted-run" };
    if (url === "/api/runs") return [];
    return state("completed", "submitted-run");
  });
  await h.get("composer").onsubmit({ preventDefault() {} });
  assert.equal(h.evaluate("selectedId"), "submitted-run");
  assert.equal(h.evaluate("current.status"), "completed");
  assert.equal(h.get("welcome").hidden, true);
});
