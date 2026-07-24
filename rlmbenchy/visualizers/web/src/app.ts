/*
 * Edit this file for web visualizer behavior.
 * `static/app.js` is generated from `src/app.ts` via `npm run build`.
 * `static/index.html` and `static/styles.css` are hand-authored files served directly.
 */

// -- Types -------------------------------------------------------------------

interface UsageSummary {
  coverage?: { total_tokens_complete?: boolean };
  generated_tokens?: number;
  prompt_tokens?: number;
  total_tokens?: number;
}

interface ActivitySummary {
  event_count?: number;
  llm_calls?: number;
  llm_errors?: number;
  tool_calls?: number;
  tool_call_errors?: number;
  subllm_calls?: number;
  subllm_errors?: number;
  repl_calls?: number;
  repl_errors?: number;
  model_steps?: number;
  final_signals?: number;
  last_event?: string;
}

interface CallSummary {
  lm?: number;
  tool?: number;
  llm_query?: number;
}

interface TraceCall {
  call_id?: string;
  correlation_id?: string;
  cost_usd?: number | null;
  duration_ms?: number | null;
  error?: string;
  generated_tokens?: number | null;
  index?: number;
  kind?: string;
  model?: string;
  name?: string;
  prompt_tokens?: number | null;
  request?: unknown;
  request_event?: string;
  request_preview?: string;
  request_timestamp?: string;
  response?: unknown;
  response_event?: string;
  response_preview?: string;
  response_timestamp?: string;
  status?: string;
  total_tokens?: number | null;
}

type NarrativeKind = "text" | "error" | "final" | "call_summary";

interface NarrativeSection {
  label: string;
  kind: NarrativeKind;
  content: string;
}

interface Step {
  call_summary?: CallSummary;
  calls?: TraceCall[];
  code?: string;
  event?: string;
  events?: string[];
  exec_error?: string;
  final_outputs?: unknown;
  finalized?: boolean;
  index?: number;
  iteration?: number | null;
  step_index?: number;
  latency_ms?: number;
  narrative_sections?: NarrativeSection[];
  observed?: unknown;
  parse_success?: boolean;
  reasoning?: string;
  status?: string;
  task?: string;
  task_id?: string;
  task_inputs?: unknown;
  timestamp?: string;
  usage_summary?: UsageSummary;
}

interface Task {
  activity_summary?: ActivitySummary;
  code?: string;
  exec_error?: string;
  final_outputs?: unknown;
  finalized?: boolean;
  index?: number;
  latency_ms?: number;
  observed?: unknown;
  parse_success?: boolean;
  reasoning?: string;
  steps?: Step[];
  task?: string;
  task_id?: string;
  task_inputs?: unknown;
  timestamp?: string;
  usage_summary?: UsageSummary;
}

interface RunSummary {
  activity_summary?: ActivitySummary;
  elapsed_ms?: number;
  event_count?: number;
  final_outputs?: unknown;
  finalization_rate?: number;
  finalized_count?: number;
  last_event?: string;
  n_tasks?: number;
  status?: string;
  stop_reason?: string;
  tasks_with_exec_error?: number;
  usage_summary?: UsageSummary;
}

interface BatchSummaryRow {
  label?: string;
  value?: string;
}

interface BatchSummary {
  batch_id?: string;
  report_file?: string | null;
  summary?: {
    correct_count?: number;
    correctness_rate?: number | null;
    elapsed_s?: number;
    finalization_rate?: number;
    finalized_count?: number;
    n_tasks?: number;
    scored_count?: number;
    tasks_with_exec_error?: number;
  };
  usage_summary?: UsageSummary;
  workload?: string;
  workload_rows?: BatchSummaryRow[];
}

interface RunPayload {
  all_steps?: Step[];
  batch_summary?: BatchSummary | null;
  log_file: string;
  run_started?: Record<string, unknown>;
  summary?: RunSummary;
  tasks?: Task[];
}

interface RunIndexRow {
  elapsed_ms?: number;
  event_count?: number;
  finalization_rate?: number;
  finalized_count?: number;
  last_event?: string;
  log_file: string;
  llm_calls?: number;
  n_tasks?: number;
  status?: string;
  subllm_calls?: number;
  task_preview?: string;
  total_tokens?: number;
}

interface RunsResponse {
  log_dir: string;
  runs: RunIndexRow[];
}

// -- State -------------------------------------------------------------------

interface AppState {
  activeRunKey: string | null;
  currentRun: RunPayload | null;
  runs: RunIndexRow[];
  selectedStepIndex: number;
}

const state: AppState = {
  runs: [],
  currentRun: null,
  selectedStepIndex: 0,
  activeRunKey: null,
};

// -- DOM refs ----------------------------------------------------------------

function el<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing #${id}`);
  return element as T;
}

const runListEl = el<HTMLDivElement>("runList");
const runCountEl = el<HTMLSpanElement>("runCount");
const refreshBtnEl = el<HTMLButtonElement>("refreshBtn");

const emptyStateEl = el<HTMLDivElement>("emptyState");
const summaryEl = el<HTMLElement>("summary");
const batchSectionEl = el<HTMLElement>("batchSection");
const batchSectionMetaEl = el<HTMLSpanElement>("batchSectionMeta");
const batchMetricsEl = el<HTMLDivElement>("batchMetrics");
const stepSectionEl = el<HTMLElement>("stepSection");
const stepSectionMetaEl = el<HTMLSpanElement>("stepSectionMeta");
const stepRailEl = el<HTMLDivElement>("stepRail");
const narrativeSectionEl = el<HTMLElement>("narrativeSection");
const narrativeTitleEl = el<HTMLHeadingElement>("narrativeTitle");
const narrativeBodyEl = el<HTMLDivElement>("narrativeBody");
const callsSectionEl = el<HTMLElement>("callsSection");
const callsTitleEl = el<HTMLHeadingElement>("callsTitle");
const callsMetaEl = el<HTMLSpanElement>("callsMeta");
const callsListEl = el<HTMLDivElement>("callsList");

const footerNoteEl = el<HTMLDivElement>("footerNote");
const statStatusEl = el<HTMLDivElement>("statStatus");
const statTasksEl = el<HTMLDivElement>("statTasks");
const statTokensEl = el<HTMLDivElement>("statTokens");
const statElapsedEl = el<HTMLDivElement>("statElapsed");
const sourceInfoEl = el<HTMLElement>("sourceInfo");

// -- Utilities ---------------------------------------------------------------

function safeInt(v: unknown, fallback = 0): number {
  if (typeof v === "number") return Number.isFinite(v) ? Math.trunc(v) : fallback;
  if (typeof v === "string") {
    const n = Number.parseFloat(v.trim());
    return Number.isFinite(n) ? Math.trunc(n) : fallback;
  }
  return fallback;
}

function fmtInt(v: unknown): string {
  if (v == null) return "n/a";
  const n = safeInt(v, NaN);
  return Number.isFinite(n) ? new Intl.NumberFormat("en-US").format(n) : "n/a";
}

function fmtMs(ms: number): string {
  if (ms <= 0) return "n/a";
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

function fmtPct(rate: unknown): string {
  if (rate == null) return "n/a";
  const n = typeof rate === "number" ? rate : Number.parseFloat(String(rate));
  if (!Number.isFinite(n)) return "n/a";
  return `${(n * 100).toFixed(0)}%`;
}

function escapeHtml(text: string): string {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function snippet(text: string, max = 80): string {
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length <= max ? clean : clean.slice(0, max - 1) + "\u2026";
}

function statusBadgeClass(status?: string): string {
  if (status === "completed" || status === "finished") return "ok";
  if (status === "error" || status === "failed") return "bad";
  if (status === "running" || status === "in_progress") return "warn";
  return "";
}

// -- API ---------------------------------------------------------------------

async function fetchRuns(): Promise<RunsResponse> {
  const resp = await fetch("/api/runs?limit=50");
  if (!resp.ok) throw new Error(`/api/runs failed: ${resp.status}`);
  return resp.json();
}

async function fetchRun(logFile: string): Promise<RunPayload> {
  const resp = await fetch(`/api/run?log=${encodeURIComponent(logFile)}`);
  if (!resp.ok) throw new Error(`/api/run failed: ${resp.status}`);
  return resp.json();
}

// -- Render: sidebar ---------------------------------------------------------

function renderRunList(): void {
  runCountEl.textContent = `${state.runs.length} run${state.runs.length !== 1 ? "s" : ""}`;
  runListEl.innerHTML = "";
  for (const run of state.runs) {
    const card = document.createElement("div");
    card.className = "run-card" + (state.activeRunKey === run.log_file ? " active" : "");
    card.addEventListener("click", () => loadRun(run.log_file));

    const logName = document.createElement("div");
    logName.className = "log-name";
    logName.textContent = run.log_file;
    card.appendChild(logName);

    const badges = document.createElement("div");
    badges.className = "run-badges";

    const statusCls = statusBadgeClass(run.status);
    badges.innerHTML = [
      `<span class="badge ${statusCls}">${escapeHtml(run.status ?? "unknown")}</span>`,
      `<span class="badge">${safeInt(run.n_tasks)} tasks</span>`,
      run.finalization_rate != null
        ? `<span class="badge">${fmtPct(run.finalization_rate)} final</span>`
        : "",
    ]
      .filter(Boolean)
      .join("");

    card.appendChild(badges);
    runListEl.appendChild(card);
  }
}

// -- Render: summary stats ---------------------------------------------------

function renderSummary(run: RunPayload): void {
  const s = run.summary;
  if (!s) {
    summaryEl.hidden = true;
    return;
  }
  summaryEl.hidden = false;

  const statusCls = statusBadgeClass(s.status);
  statStatusEl.innerHTML = `<span class="badge ${statusCls}">${escapeHtml(s.status ?? "unknown")}</span>`;

  const nTasks = safeInt(s.n_tasks);
  const steps = run.all_steps ?? [];
  statTasksEl.textContent = `${nTasks} / ${steps.length}`;

  const tokens = safeInt(s.usage_summary?.total_tokens);
  statTokensEl.textContent = tokens > 0 ? fmtInt(tokens) : "n/a";

  statElapsedEl.textContent = fmtMs(safeInt(s.elapsed_ms));
}

// -- Render: batch -----------------------------------------------------------

function renderBatch(run: RunPayload): void {
  const batch = run.batch_summary;
  if (!batch || !batch.summary) {
    batchSectionEl.hidden = true;
    return;
  }
  batchSectionEl.hidden = false;

  const bs = batch.summary;
  batchSectionMetaEl.textContent = batch.workload ?? batch.batch_id ?? "";

  const cards: Array<{ label: string; value: string }> = [
    { label: "Tasks", value: fmtInt(bs.n_tasks) },
    { label: "Finalized", value: `${fmtInt(bs.finalized_count)} (${fmtPct(bs.finalization_rate)})` },
    { label: "Correct", value: bs.correctness_rate != null ? fmtPct(bs.correctness_rate) : "n/a" },
    { label: "Errors", value: fmtInt(bs.tasks_with_exec_error) },
    { label: "Elapsed", value: bs.elapsed_s != null ? fmtMs(Math.round(bs.elapsed_s * 1000)) : "n/a" },
  ];

  // Include workload_rows if present
  if (batch.workload_rows) {
    for (const row of batch.workload_rows) {
      if (row.label && row.value) {
        cards.push({ label: row.label, value: row.value });
      }
    }
  }

  batchMetricsEl.innerHTML = cards
    .map(
      (c) =>
        `<div class="batch-card"><div class="batch-label">${escapeHtml(c.label)}</div><div class="batch-value">${escapeHtml(c.value)}</div></div>`,
    )
    .join("");
}

// -- Render: step rail -------------------------------------------------------

function renderStepRail(run: RunPayload): void {
  const steps = run.all_steps ?? [];
  if (steps.length === 0) {
    stepSectionEl.hidden = true;
    return;
  }
  stepSectionEl.hidden = false;

  // Group step count by task
  const taskIds = new Set(steps.map((s) => s.task_id ?? ""));
  stepSectionMetaEl.textContent = `${steps.length} steps across ${taskIds.size} task${taskIds.size !== 1 ? "s" : ""}`;

  stepRailEl.innerHTML = "";
  let prevTaskId: string | undefined;

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];

    // Insert a visual separator when the task changes
    if (step.task_id !== prevTaskId && prevTaskId !== undefined) {
      const sep = document.createElement("div");
      sep.style.cssText = "width:2px;background:var(--border);flex:0 0 auto;border-radius:1px;margin:0 0.15rem;";
      stepRailEl.appendChild(sep);
    }
    prevTaskId = step.task_id;

    const card = document.createElement("div");
    const statusCls = step.status === "final" ? "final" : step.status === "error" ? "error" : "ok";
    card.className = `step-card ${statusCls}${i === state.selectedStepIndex ? " active" : ""}`;
    card.addEventListener("click", () => selectStep(i));

    const stepNum = step.step_index ?? step.iteration ?? i + 1;
    const label = step.finalized ? "SUBMIT" : step.exec_error ? "ERR" : `Step ${stepNum}`;
    card.innerHTML = `<div class="step-num">${escapeHtml(String(label))}</div><div class="step-status">${escapeHtml(snippet(step.task ?? "", 20))}</div>`;

    stepRailEl.appendChild(card);
  }

  // Scroll selected card into view
  const activeCard = stepRailEl.querySelector(".step-card.active");
  if (activeCard) {
    activeCard.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }
}

// -- Render: narrative -------------------------------------------------------

const NARRATIVE_KIND_CLASS: Record<NarrativeKind, string> = {
  text: "",
  error: "error-text",
  final: "final-text",
  call_summary: "",
};

function renderNarrative(run: RunPayload): void {
  const steps = run.all_steps ?? [];
  if (steps.length === 0) {
    narrativeSectionEl.hidden = true;
    return;
  }
  narrativeSectionEl.hidden = false;

  const step = steps[state.selectedStepIndex];
  if (!step) {
    narrativeBodyEl.innerHTML = "<pre>No step data.</pre>";
    return;
  }

  const stepNum = step.step_index ?? step.iteration ?? state.selectedStepIndex + 1;
  narrativeTitleEl.textContent = `Step ${stepNum} — ${snippet(step.task ?? "", 60)}`;

  const sections = step.narrative_sections ?? [];
  const parts: string[] = [];
  for (const section of sections) {
    const label = escapeHtml(section.label);
    const content = escapeHtml(section.content);
    if (section.kind === "call_summary") {
      parts.push(`<div class="call-summary-line">${label}: ${content}</div>`);
      continue;
    }
    const cls = NARRATIVE_KIND_CLASS[section.kind] ?? "";
    const pre = cls ? `<pre class="${cls}">${content}</pre>` : `<pre>${content}</pre>`;
    parts.push(`<div class="section-label">${label}</div>${pre}`);
  }

  narrativeBodyEl.innerHTML = parts.length > 0 ? parts.join("") : "<pre>No data for this step.</pre>";
}

// -- Render: calls -----------------------------------------------------------

function renderCalls(run: RunPayload): void {
  const steps = run.all_steps ?? [];
  const step = steps[state.selectedStepIndex];
  const calls = step?.calls ?? [];

  if (calls.length === 0) {
    callsSectionEl.hidden = true;
    return;
  }
  callsSectionEl.hidden = false;

  callsTitleEl.textContent = "Calls";
  callsMetaEl.textContent = `${calls.length} call${calls.length !== 1 ? "s" : ""}`;

  callsListEl.innerHTML = "";
  for (const call of calls) {
    const card = document.createElement("div");
    card.className = "call-card";

    const kindLabel = call.kind ?? "unknown";
    const nameLabel = call.name ?? "";
    const statusLabel = call.status ?? "";
    const statusCls = statusLabel === "error" ? "bad" : statusLabel === "ok" ? "ok" : "";

    const headerHtml = `<div class="call-header"><span class="badge">${escapeHtml(kindLabel)}</span> <strong>${escapeHtml(nameLabel)}</strong> <span class="badge ${statusCls}">${escapeHtml(statusLabel)}</span></div>`;

    const metaParts: string[] = [];
    if (call.duration_ms != null) metaParts.push(fmtMs(call.duration_ms));
    if (call.total_tokens != null) metaParts.push(`${fmtInt(call.total_tokens)} tok`);
    if (call.model) metaParts.push(call.model);
    const metaHtml = metaParts.length > 0 ? `<div class="call-meta">${escapeHtml(metaParts.join(" | "))}</div>` : "";

    // Collapsible request/response
    let detailsHtml = "";
    const reqPreview = call.request_preview ?? "";
    const respPreview = call.response_preview ?? "";
    const errorText = call.error ?? "";

    if (reqPreview || respPreview || errorText || call.request || call.response) {
      const detailParts: string[] = [];

      if (errorText) {
        detailParts.push(`<pre style="color:var(--bad)">${escapeHtml(errorText)}</pre>`);
      }
      if (reqPreview) {
        detailParts.push(`<pre>${escapeHtml(reqPreview)}</pre>`);
      } else if (call.request) {
        detailParts.push(`<pre>${escapeHtml(typeof call.request === "string" ? call.request : JSON.stringify(call.request, null, 2))}</pre>`);
      }
      if (respPreview) {
        detailParts.push(`<pre>${escapeHtml(respPreview)}</pre>`);
      } else if (call.response) {
        detailParts.push(`<pre>${escapeHtml(typeof call.response === "string" ? call.response : JSON.stringify(call.response, null, 2))}</pre>`);
      }

      detailsHtml = `<details><summary>Show detail</summary>${detailParts.join("")}</details>`;
    }

    card.innerHTML = headerHtml + metaHtml + detailsHtml;
    callsListEl.appendChild(card);
  }
}

// -- Render: source info footer ----------------------------------------------

function renderSourceInfo(run: RunPayload): void {
  const modelId = typeof run.run_started?.model_id === "string" ? run.run_started.model_id : "";
  const model = modelId || (typeof run.run_started?.model === "string" ? run.run_started.model : "");
  const workload = run.run_started?.workload ?? "";
  const parts: string[] = [run.log_file];
  if (workload) parts.push(String(workload));
  if (model) parts.push(String(model));
  sourceInfoEl.textContent = parts.join(" | ");
}

// -- Render all --------------------------------------------------------------

function renderRun(): void {
  const run = state.currentRun;
  if (!run) {
    emptyStateEl.hidden = false;
    summaryEl.hidden = true;
    batchSectionEl.hidden = true;
    stepSectionEl.hidden = true;
    narrativeSectionEl.hidden = true;
    callsSectionEl.hidden = true;
    footerNoteEl.hidden = true;
    sourceInfoEl.textContent = "-";
    return;
  }
  emptyStateEl.hidden = true;
  footerNoteEl.hidden = false;

  renderSummary(run);
  renderBatch(run);
  renderStepRail(run);
  renderNarrative(run);
  renderCalls(run);
  renderSourceInfo(run);
}

// -- Actions -----------------------------------------------------------------

async function loadRuns(): Promise<void> {
  try {
    const data = await fetchRuns();
    state.runs = data.runs ?? [];
    renderRunList();
  } catch (err) {
    console.error("Failed to load runs:", err);
  }
}

async function loadRun(logFile: string): Promise<void> {
  state.activeRunKey = logFile;
  renderRunList(); // highlight immediately

  try {
    const run = await fetchRun(logFile);
    state.currentRun = run;
    state.selectedStepIndex = 0;
    renderRun();
  } catch (err) {
    console.error("Failed to load run:", err);
  }
}

function selectStep(index: number): void {
  if (!state.currentRun) return;
  const steps = state.currentRun?.all_steps ?? [];
  if (index < 0 || index >= steps.length) return;
  state.selectedStepIndex = index;
  renderStepRail(state.currentRun);
  renderNarrative(state.currentRun);
  renderCalls(state.currentRun);
}

// -- Keyboard navigation -----------------------------------------------------

document.addEventListener("keydown", (e) => {
  if (!state.currentRun) return;
  const steps = state.currentRun?.all_steps ?? [];
  if (steps.length === 0) return;

  if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    e.preventDefault();
    selectStep(Math.max(0, state.selectedStepIndex - 1));
  } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    e.preventDefault();
    selectStep(Math.min(steps.length - 1, state.selectedStepIndex + 1));
  } else if (e.key === "Home") {
    e.preventDefault();
    selectStep(0);
  } else if (e.key === "End") {
    e.preventDefault();
    selectStep(steps.length - 1);
  }
});

// -- Init --------------------------------------------------------------------

refreshBtnEl.addEventListener("click", loadRuns);

loadRuns();
