// logger.ts
// Lightweight, console-friendly logger with topics, levels, per-topic defaults,
// and environment/browser overrides (URL, localStorage, process.env).

// ---------- Types & constants ----------

export type Level = "trace" | "debug" | "info" | "warn" | "error" | "fatal";
export type Topic = string;

const LEVELS: Level[] = ["trace", "debug", "info", "warn", "error", "fatal"];
const LEVEL_INDEX: Record<Level, number> = {
  trace: 0, debug: 1, info: 2, warn: 3, error: 4, fatal: 5
};

export type TransportRecord = {
  time: number;
  level: Level;
  topic: Topic;
  msg: unknown[];
};

export type TransportFn = (rec: TransportRecord) => void;

export type Config = {
  /** Glob/wildcard map, e.g. {"auth:*":"debug","db":"warn"} */
  minLevelByTopic?: Record<string, Level>;
  /** Final sink. Defaults to a browser/Node-aware console/stdout transport. */
  transport?: TransportFn;
};

type CreateLoggerOpts = {
  /** Per-topic baked-in default minimum level (before overrides). */
  defaultLevel?: Level;
};

// ---------- Internal state ----------

let config: Required<Config> = {
  minLevelByTopic: {},
  transport: defaultTransport()
};

// Cache compiled regex for wildcard patterns
const _patternCache = new Map<string, RegExp>();

// ---------- Public API ----------

/**
 * Merge global configuration. Safe to call multiple times (last-write-wins).
 * You can pass either a mapping or a textual spec (see `applyDebugSpec`).
 */
export function setupLogger(newConfig: Partial<Config & { debugSpec?: string }>) {
  if (newConfig.minLevelByTopic) {
    config.minLevelByTopic = { ...config.minLevelByTopic, ...newConfig.minLevelByTopic };
  }
  if (newConfig.transport) {
    config.transport = newConfig.transport;
  }
  if (newConfig.debugSpec) {
    applyDebugSpec(newConfig.debugSpec);
  }
}

/**
 * Convenience: reads overrides from env/localStorage/URL, then applies them.
 * Browser: `?debug=auth:trace,db:warn` or `localStorage.debug`.
 * Node: `process.env.DEBUG_LEVELS` (same format).
 */
export function autoConfigureFromEnvironment() {
  // Browser URL and localStorage
  const isBrowser = typeof window !== "undefined" && typeof document !== "undefined";
  if (isBrowser) {
    try {
      const urlVal = new URLSearchParams(window.location.search).get("debug") || "";
      const lsVal = window.localStorage?.getItem("debug") || "";
      const combined = [urlVal, lsVal].filter(Boolean).join(",");
      if (combined) applyDebugSpec(combined);
    } catch { /* ignore */ }
  }

  // Node env
  if (typeof process !== "undefined" && process?.env) {
    const envVal = process.env.DEBUG_LEVELS || process.env.DEBUG || ""; // accept both
    if (envVal) applyDebugSpec(envVal);
  }
}

/**
 * Create a topic logger. You can bake a per-topic default minimum level that
 * will be used unless overridden by global/environment config.
 */
export function createLogger(topic: Topic, opts?: CreateLoggerOpts) {
  const defaultLevel: Level = opts?.defaultLevel ?? "info";

  const emit = (level: Level) => (...msg: unknown[]) => {
    if (isEnabled(topic, level, defaultLevel)) {
      config.transport({ time: Date.now(), level, topic, msg });
    }
  };

  return {
    topic,
    trace: emit("trace"),
    debug: emit("debug"),
    info:  emit("info"),
    warn:  emit("warn"),
    error: emit("error"),
    fatal: emit("fatal"),
  };
}

// ---------- Helpers ----------

function isEnabled(topic: string, level: Level, defaultLevel: Level): boolean {
  const globalMin = lookupGlobalMinLevel(topic, config.minLevelByTopic);
  const min = globalMin ?? defaultLevel;
  return LEVEL_INDEX[level] >= LEVEL_INDEX[min];
}

function lookupGlobalMinLevel(topic: string, table: Record<string, Level>): Level | undefined {
  // First try exact match for speed
  if (table[topic]) return table[topic];
  // Then wildcard patterns
  for (const [pattern, lvl] of Object.entries(table)) {
    if (pattern === topic) continue;
    const re = _patternCache.get(pattern) ?? compileGlob(pattern);
    _patternCache.set(pattern, re);
    if (re.test(topic)) return lvl;
  }
}

function compileGlob(glob: string): RegExp {
  // Convert '*' -> '.*' and escape regex meta
  const escaped = glob.replace(/[-/\\^$+?.()|[\]{}]/g, "\\$&").replace(/\*/g, ".*");
  return new RegExp(`^${escaped}$`);
}

/**
 * Parse and apply a textual mapping like:
 *   "auth,db:warn,auth:token:trace,ui:*:debug"
 * Supported separators:
 *   ',' between entries
 *   ':' or '=' between pattern and level
 * If level omitted -> "debug". Whitespace ignored.
 */
function applyDebugSpec(spec: string) {
  const map: Record<string, Level> = {};
  spec.split(",").map(s => s.trim()).filter(Boolean).forEach(entry => {
    // Accept "pattern:level", "pattern=level", or just "pattern" (=> debug)
    const m = entry.match(/^(.+?)(?::|=)?(trace|debug|info|warn|error|fatal)?$/i);
    if (!m) return;
    const pattern = (m[1] || "").trim();
    const lvl = ((m[2] || "debug").toLowerCase()) as Level;
    if (!pattern) return;
    map[pattern] = lvl;
  });
  config.minLevelByTopic = { ...config.minLevelByTopic, ...map };
}

function defaultTransport(): TransportFn {
  const isBrowser = typeof window !== "undefined" && typeof document !== "undefined";
  if (isBrowser) {
    // Pretty console with topic label; keeps DevTools level filtering.
    return ({ level, topic, msg }) => {
      const prefix = `%c[${topic}]`;
      const style = "font-weight:600";
      const out =
        level === "warn" ? console.warn
        : level === "error" || level === "fatal" ? console.error
        : level === "info" ? console.info
        : level === "debug" ? console.debug
        : console.log;
      out(prefix, style, ...msg);
    };
  }

  // Node: fast-ish line-delimited JSON to stdout/stderr by level
  return ({ time, level, topic, msg }) => {
    const rec = { time, level, topic, msg };
    const line = JSON.stringify(rec) + "\n";
    if (LEVEL_INDEX[level] >= LEVEL_INDEX.warn) {
      // warn and above -> stderr
      try { (process.stderr as any).write(line); } catch { /* ignore */ }
    } else {
      try { (process.stdout as any).write(line); } catch { /* ignore */ }
    }
  };
}

// ---------- Optional: eager environment load ----------
// Call this once at app boot (or let callers invoke manually).
// Comment out if you prefer explicit control.
//autoConfigureFromEnvironment();

// ---------- Usage examples (remove if you like) ----------
// const log = createLogger("auth", { defaultLevel: "debug" });
// log.debug("user logged in", { id: 123 });
// const dbLog = createLogger("db", { defaultLevel: "warn" });
// dbLog.error("query failed", new Error("boom"));
