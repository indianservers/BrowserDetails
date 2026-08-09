const SDK_VERSION = "0.2.0";

type ConsentMode = "explicit" | "implied";
type ConsentState = "GRANTED" | "DENIED" | "WITHDRAWN" | "IMPLIED";
type SessionState = "ACTIVE" | "IDLE" | "BACKGROUND" | "OFFLINE" | "CONSENT_WITHDRAWN";
type QueueItem = { id: string; name: string; payload: Record<string, unknown>; createdAt: number };

type InitOptions = {
  projectId: string;
  endpoint: string;
  consent?: boolean;
  consentMode?: ConsentMode;
  collectPerformance?: boolean;
  collectErrors?: boolean;
  collectPageTitle?: boolean;
  appVersion?: string;
  allowedSupportUrls?: string[];
  approvedEventNames?: string[];
  approvedMetadataKeys?: string[];
  maxQueueSize?: number;
  maxQueueAgeMs?: number;
  heartbeatSeconds?: number;
  idleAfterMs?: number;
  redactUrlQuery?: boolean;
  healthCheck?: () => Promise<Record<string, unknown>> | Record<string, unknown>;
  diagnosticLogProvider?: () => Promise<Record<string, unknown>> | Record<string, unknown>;
};

const defaultOptions = {
  maxQueueSize: 25,
  maxQueueAgeMs: 5 * 60 * 1000,
  heartbeatSeconds: 20,
  idleAfterMs: 120000,
  redactUrlQuery: true
};

let options: (InitOptions & typeof defaultOptions) | null = null;
let sessionId = "";
let visitorId = "";
let consentState: ConsentState = "DENIED";
let socket: WebSocket | null = null;
let heartbeatTimer: number | null = null;
let flushTimer: number | null = null;
let actionPollTimer: number | null = null;
let reconnectAttempts = 0;
let activityAt = Date.now();
let registered = false;
let lastRoute = "";
let webSocketUrl = "";
let performanceSnapshot: Record<string, unknown> = {};
let installed = false;
const eventQueue: QueueItem[] = [];
const cleanupCallbacks: Array<() => void> = [];

const sensitivePattern = /(password|passcode|otp|token|secret|cookie|authorization|email|phone|card|cvv|ssn|social|bearer|jwt)/i;
const tokenLikePattern = /(?:eyJ[a-zA-Z0-9_-]{10,}|[a-f0-9]{32,}|[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)/;

function randomId(prefix: string): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `${prefix}_${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage can be disabled; the active session still works without persistence.
  }
}

function storageRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // No-op for disabled storage.
  }
}

function storedVisitorId(): string {
  const key = "clientMonitor.visitorId";
  const existing = storageGet(key);
  if (existing) return existing;
  const next = randomId("visitor");
  storageSet(key, next);
  return next;
}

function endpoint(path: string): string {
  return `${options?.endpoint.replace(/\/$/, "")}${path}`;
}

export function safeRoute(raw = `${location.pathname}${location.search}${location.hash || ""}`): string {
  try {
    const url = new URL(raw, location.origin);
    const route = options?.redactUrlQuery === false ? `${url.pathname}${url.search}${url.hash}` : `${url.pathname}${url.hash}`;
    return route.slice(0, 1024);
  } catch {
    return raw.split("?", 1)[0].slice(0, 1024);
  }
}

function referrerOrigin(): string | null {
  if (!document.referrer) return null;
  try {
    return new URL(document.referrer).origin;
  } catch {
    return null;
  }
}

function classifyDevice(): string {
  const width = Math.min(screen.width || innerWidth, innerWidth || screen.width);
  if (width < 760) return "mobile";
  if (width < 1100 || navigator.maxTouchPoints > 1) return "tablet";
  return "desktop";
}

function browserFamily(): string {
  const ua = navigator.userAgent;
  if (/Edg\//.test(ua)) return "Edge";
  if (/OPR\//.test(ua)) return "Opera";
  if (/Firefox\//.test(ua)) return "Firefox";
  if (/Chrome\//.test(ua)) return "Chrome";
  if (/Safari\//.test(ua)) return "Safari";
  return "Unknown";
}

function renderingEngine(): string {
  const ua = navigator.userAgent;
  if (/Gecko\/\d/.test(ua) && /Firefox\//.test(ua)) return "Gecko";
  if (/AppleWebKit\//.test(ua) && /Chrome|Safari|Edg|OPR/.test(ua)) return "Blink/WebKit";
  return "Unknown";
}

function supports(fn: () => void): boolean {
  try {
    fn();
    return true;
  } catch {
    return false;
  }
}

function getConnection() {
  return (navigator as Navigator & {
    connection?: { effectiveType?: string; downlink?: number; rtt?: number; saveData?: boolean; type?: string };
  }).connection;
}

function collectWebGl() {
  const canvas = document.createElement("canvas");
  const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
  const webgl = gl as WebGLRenderingContext | null;
  if (!webgl) return { webglVersion: "unsupported", webglRenderer: null, maxTextureSize: null };
  return {
    webglVersion: "WebGL 1",
    webglRenderer: webgl.getParameter(webgl.RENDERER),
    maxTextureSize: webgl.getParameter(webgl.MAX_TEXTURE_SIZE)
  };
}

export function collectDiagnostics() {
  const nav = navigator as Navigator & {
    userAgentData?: unknown;
    globalPrivacyControl?: boolean;
  };
  const connection = getConnection();
  const webgl = collectWebGl();
  return {
    browser: {
      userAgent: navigator.userAgent,
      userAgentData: nav.userAgentData || null,
      family: browserFamily(),
      version: navigator.userAgent.match(/(?:Chrome|Firefox|Safari|Edg)\/([\d.]+)/)?.[1] || null,
      renderingEngine: renderingEngine(),
      language: navigator.language,
      languages: navigator.languages,
      platform: navigator.platform,
      os: navigator.platform,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      utcOffsetMinutes: new Date().getTimezoneOffset(),
      cookiesEnabled: navigator.cookieEnabled,
      localStorage: supports(() => {
        localStorage.setItem("__cm_test", "1");
        localStorage.removeItem("__cm_test");
      }),
      sessionStorage: supports(() => {
        sessionStorage.setItem("__cm_test", "1");
        sessionStorage.removeItem("__cm_test");
      }),
      indexedDB: "indexedDB" in window,
      websocket: "WebSocket" in window,
      webAssembly: "WebAssembly" in window,
      webWorker: "Worker" in window,
      serviceWorkerCapability: "serviceWorker" in navigator,
      notificationsCapability: "Notification" in window,
      notificationsPermission: "Notification" in window ? Notification.permission : "unsupported",
      touchSupport: "ontouchstart" in window,
      pointerType: matchMedia("(pointer: coarse)").matches ? "coarse" : matchMedia("(pointer: fine)").matches ? "fine" : "none",
      maxTouchPoints: navigator.maxTouchPoints,
      pdfViewerEnabled: "pdfViewerEnabled" in navigator ? (navigator as Navigator & { pdfViewerEnabled?: boolean }).pdfViewerEnabled : null,
      doNotTrack: navigator.doNotTrack,
      globalPrivacyControl: Boolean(nav.globalPrivacyControl)
    },
    display: {
      screenWidth: screen.width,
      screenHeight: screen.height,
      availableWidth: screen.availWidth,
      availableHeight: screen.availHeight,
      viewportWidth: innerWidth,
      viewportHeight: innerHeight,
      devicePixelRatio,
      orientation: screen.orientation?.type,
      colorDepth: screen.colorDepth,
      fullscreenCapability: "fullscreenEnabled" in document ? document.fullscreenEnabled : false,
      deviceCategory: classifyDevice(),
      colorPreference: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
      highContrast: matchMedia("(prefers-contrast: more)").matches
    },
    graphics: {
      canvas: "HTMLCanvasElement" in window,
      svg: Boolean(document.createElementNS),
      ...webgl,
      hardwareAcceleration: webgl.webglVersion !== "unsupported" ? "likely" : "unknown",
      cssTransforms2d: CSS.supports("transform", "translateX(1px)"),
      cssTransforms3d: CSS.supports("transform", "translate3d(1px, 1px, 1px)"),
      animation: CSS.supports("animation-name", "fade")
    },
    network: {
      online: navigator.onLine,
      effectiveType: connection?.effectiveType,
      downlink: connection?.downlink,
      rtt: connection?.rtt,
      saveData: connection?.saveData,
      connectionType: connection?.type,
      https: location.protocol === "https:"
    },
    page: {
      origin: location.origin,
      route: safeRoute(),
      title: options?.collectPageTitle ? document.title.slice(0, 180) : undefined,
      referrerOrigin: referrerOrigin(),
      visibility: document.visibilityState,
      focused: document.hasFocus(),
      loadTimestamp: performance.timeOrigin,
      navigationType: performance.getEntriesByType("navigation")[0]?.entryType || "navigation",
      performance: performanceSnapshot
    }
  };
}

function currentState(): SessionState {
  if (consentState === "WITHDRAWN") return "CONSENT_WITHDRAWN";
  if (!navigator.onLine) return "OFFLINE";
  if (document.visibilityState === "hidden") return "BACKGROUND";
  return Date.now() - activityAt > (options?.idleAfterMs || defaultOptions.idleAfterMs) ? "IDLE" : "ACTIVE";
}

async function post(path: string, body: unknown, keepalive = false) {
  if (!options || consentState === "DENIED") return null;
  return fetch(endpoint(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "omit",
    keepalive
  });
}

function shouldMonitor(): boolean {
  return Boolean(options && consentState !== "DENIED" && consentState !== "WITHDRAWN");
}

function consentPayload() {
  return {
    project_id: options?.projectId,
    session_id: sessionId,
    visitor_id: visitorId,
    consent_state: consentState
  };
}

async function register() {
  if (!options || !shouldMonitor()) return;
  const response = await post("/api/client/register", {
    project_id: options.projectId,
    session_id: sessionId,
    visitor_id: visitorId,
    origin: location.origin,
    route: safeRoute(),
    referrer_origin: referrerOrigin(),
    consent_state: consentState,
    sdk_version: SDK_VERSION,
    app_version: options.appVersion,
    diagnostics: collectDiagnostics()
  });
  if (!response?.ok) return;
  const body = await response.json();
  registered = true;
  webSocketUrl = body.websocket_url;
  connectSocket(webSocketUrl);
  startHeartbeat(body.heartbeat_interval_seconds || options.heartbeatSeconds);
  startQueueFlush();
  startActionPolling();
  void flushQueue();
}

function connectSocket(url: string) {
  if (!shouldMonitor() || !("WebSocket" in window)) return;
  socket?.close();
  socket = new WebSocket(url);
  socket.onopen = () => {
    reconnectAttempts = 0;
    void emitSafeEvent("reconnected", { transport: "websocket" });
  };
  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === "diagnostic_action") void handleAction(message.action);
    } catch {
      void emitSafeEvent("sdk_error", { reason: "invalid_websocket_message" });
    }
  };
  socket.onclose = () => {
    if (!shouldMonitor()) return;
    const delay = Math.min(30000, 1000 * 2 ** reconnectAttempts) + Math.random() * 750;
    reconnectAttempts += 1;
    window.setTimeout(() => connectSocket(url), delay);
  };
}

function startHeartbeat(seconds: number) {
  if (heartbeatTimer) window.clearInterval(heartbeatTimer);
  heartbeatTimer = window.setInterval(() => void sendHeartbeat(), seconds * 1000);
}

async function sendHeartbeat() {
  if (!registered || !options) return;
  await post("/api/client/heartbeat", {
    session_id: sessionId,
    project_id: options.projectId,
    state: currentState(),
    route: safeRoute(),
    visible: document.visibilityState === "visible"
  }, true);
}

function startQueueFlush() {
  if (flushTimer) window.clearInterval(flushTimer);
  flushTimer = window.setInterval(() => void flushQueue(), 5000);
}

function startActionPolling() {
  if (actionPollTimer) window.clearInterval(actionPollTimer);
  actionPollTimer = window.setInterval(() => void pollPendingActions(), 7000);
}

async function pollPendingActions() {
  if (!registered || !shouldMonitor() || !options) return;
  const url = `${endpoint("/api/client/actions")}?session_id=${encodeURIComponent(sessionId)}&project_id=${encodeURIComponent(options.projectId)}`;
  const response = await fetch(url, { method: "GET", credentials: "omit", cache: "no-store" });
  if (!response.ok) return;
  const actions = await response.json();
  if (!Array.isArray(actions)) return;
  for (const action of actions) await handleAction(action);
}

export function scrubPayload(payload: Record<string, unknown>, approvedKeys?: string[]): Record<string, unknown> {
  const clean: Record<string, unknown> = {};
  const allowed = approvedKeys ? new Set(approvedKeys) : null;
  for (const [key, value] of Object.entries(payload || {})) {
    if (allowed && !allowed.has(key)) continue;
    if (sensitivePattern.test(key)) {
      clean[key] = "[REDACTED]";
    } else if (typeof value === "string") {
      clean[key] = scrubString(value);
    } else if (typeof value === "number" || typeof value === "boolean" || value == null) {
      clean[key] = value;
    } else if (Array.isArray(value)) {
      clean[key] = value.slice(0, 20).map((item) => typeof item === "string" ? scrubString(item) : item);
    } else if (typeof value === "object") {
      clean[key] = scrubPayload(value as Record<string, unknown>, approvedKeys);
    }
  }
  return clean;
}

function scrubString(value: string): string {
  return tokenLikePattern.test(value) || /@|\+?\d[\d -]{7,}/.test(value) ? "[REDACTED]" : value.slice(0, 512);
}

function isSensitiveInput(value: string): boolean {
  return sensitivePattern.test(value) || scrubString(value) === "[REDACTED]";
}

function enqueue(name: string, payload: Record<string, unknown>): QueueItem {
  const item = { id: randomId("event"), name, payload, createdAt: Date.now() };
  eventQueue.push(item);
  trimQueue();
  return item;
}

function trimQueue() {
  if (!options) return;
  const cutoff = Date.now() - options.maxQueueAgeMs;
  while (eventQueue.length && eventQueue[0].createdAt < cutoff) eventQueue.shift();
  while (eventQueue.length > options.maxQueueSize) eventQueue.shift();
}

async function flushQueue() {
  if (!registered || !shouldMonitor()) return;
  trimQueue();
  while (eventQueue.length) {
    const item = eventQueue[0];
    const response = await post("/api/client/events", {
      event_id: item.id,
      session_id: sessionId,
      project_id: options?.projectId,
      name: item.name,
      payload: item.payload
    });
    if (!response?.ok) break;
    eventQueue.shift();
  }
}

async function emitSafeEvent(name: string, payload: Record<string, unknown> = {}) {
  enqueue(name, scrubPayload(payload, options?.approvedMetadataKeys));
  await flushQueue();
}

function validateEvent(name: string, payload: Record<string, unknown>) {
  if (!/^[a-zA-Z0-9_.:-]{1,128}$/.test(name)) throw new Error("Invalid event name.");
  if (options?.approvedEventNames?.length && !options.approvedEventNames.includes(name)) {
    throw new Error("Event name is not approved.");
  }
  if (JSON.stringify(payload).length > 4096) throw new Error("Event payload is too large.");
}

function addListener(target: EventTarget, event: string, handler: EventListenerOrEventListenerObject, listenerOptions?: AddEventListenerOptions) {
  target.addEventListener(event, handler, listenerOptions);
  cleanupCallbacks.push(() => target.removeEventListener(event, handler, listenerOptions));
}

function installLifecycleListeners() {
  if (installed) return;
  installed = true;
  ["click", "mousemove", "scroll", "focus", "touchstart"].forEach((event) => {
    addListener(window, event, () => {
      activityAt = Date.now();
    }, { passive: true });
  });
  addListener(document, "visibilitychange", () => {
    void sendHeartbeat();
    void emitSafeEvent(document.visibilityState === "visible" ? "page_visible" : "page_hidden", { route: safeRoute() });
  });
  addListener(window, "online", () => {
    void sendHeartbeat();
    void emitSafeEvent("network_online", {});
  });
  addListener(window, "offline", () => {
    void sendHeartbeat();
    void emitSafeEvent("network_offline", {});
  });
  addListener(window, "resize", debounce(() => {
    void emitSafeEvent("viewport_changed", { width: innerWidth, height: innerHeight });
  }, 750));
  addListener(window, "focus", () => void emitSafeEvent("browser_focused", {}));
  addListener(window, "blur", () => void emitSafeEvent("browser_blurred", {}));
  installRouteObserver();
}

function installRouteObserver() {
  lastRoute = safeRoute();
  const check = () => {
    const next = safeRoute();
    if (next !== lastRoute) {
      lastRoute = next;
      void emitSafeEvent("route_changed", { route: next });
      void sendHeartbeat();
    }
  };
  const originalPush = history.pushState;
  const originalReplace = history.replaceState;
  history.pushState = function (...args) {
    const result = originalPush.apply(this, args);
    check();
    return result;
  };
  history.replaceState = function (...args) {
    const result = originalReplace.apply(this, args);
    check();
    return result;
  };
  addListener(window, "popstate", check);
  cleanupCallbacks.push(() => {
    history.pushState = originalPush;
    history.replaceState = originalReplace;
  });
}

function installPerformanceCollection() {
  if (!options?.collectPerformance || !("PerformanceObserver" in window)) return;
  const observe = (type: string, handler: (entry: PerformanceEntry) => void) => {
    try {
      const observer = new PerformanceObserver((list) => list.getEntries().forEach(handler));
      observer.observe({ type, buffered: true });
      cleanupCallbacks.push(() => observer.disconnect());
    } catch {
      // Older browsers may not support every metric type.
    }
  };
  observe("navigation", (entry) => {
    const nav = entry as PerformanceNavigationTiming;
    performanceSnapshot = {
      ...performanceSnapshot,
      domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
      loadMs: Math.round(nav.loadEventEnd - nav.startTime)
    };
  });
  observe("paint", (entry) => {
    performanceSnapshot = { ...performanceSnapshot, [entry.name.replace(/-/g, "_")]: Math.round(entry.startTime) };
  });
  observe("largest-contentful-paint", (entry) => {
    performanceSnapshot = { ...performanceSnapshot, largest_contentful_paint: Math.round(entry.startTime) };
  });
  observe("layout-shift", (entry: PerformanceEntry & { value?: number; hadRecentInput?: boolean }) => {
    if (!entry.hadRecentInput) {
      performanceSnapshot = { ...performanceSnapshot, cumulative_layout_shift: Number(((Number(performanceSnapshot.cumulative_layout_shift) || 0) + (entry.value || 0)).toFixed(4)) };
    }
  });
  observe("event", (entry) => {
    performanceSnapshot = { ...performanceSnapshot, interaction_to_next_paint: Math.round(entry.duration) };
  });
}

function sanitizeErrorText(value: unknown): string {
  return scrubString(String(value || "Unknown error")).replace(/\?.*?(?=\s|$)/g, "?[REDACTED]");
}

function installErrorCollection() {
  if (!options?.collectErrors) return;
  addListener(window, "error", (event) => {
    const error = event as ErrorEvent;
    void emitSafeEvent("application_error", {
      message: sanitizeErrorText(error.message),
      source_file: sanitizeErrorText(error.filename || ""),
      line: error.lineno,
      column: error.colno,
      route: safeRoute()
    });
  });
  addListener(window, "unhandledrejection", (event) => {
    const rejection = event as PromiseRejectionEvent;
    void emitSafeEvent("application_error", {
      message: sanitizeErrorText(rejection.reason?.message || rejection.reason),
      route: safeRoute()
    });
  });
}

function debounce(fn: () => void, wait: number) {
  let timer: number | null = null;
  return () => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(fn, wait);
  };
}

function confirmAndRun(message: string, fn: () => void): boolean {
  if (window.confirm(message)) {
    fn();
    return true;
  }
  return false;
}

function supportUrlAllowed(url: string): boolean {
  if (!options?.allowedSupportUrls?.length) return false;
  try {
    const requested = new URL(url, location.origin).toString();
    return options.allowedSupportUrls.some((allowed) => new URL(allowed, location.origin).toString() === requested);
  } catch {
    return false;
  }
}

function urlIsDisplaySafe(url: string): boolean {
  try {
    const parsed = new URL(url, location.origin);
    return ["https:", "http:"].includes(parsed.protocol) && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

function supportOverlayBase(title: string) {
  document.getElementById("client-monitor-support-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "client-monitor-support-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:rgba(15,23,42,.56);display:grid;place-items:center;padding:18px;font-family:system-ui,-apple-system,Segoe UI,sans-serif;";
  const panel = document.createElement("div");
  panel.style.cssText = "width:min(520px,100%);max-height:min(720px,92vh);overflow:auto;background:#fff;color:#172033;border-radius:10px;border:1px solid #d5d9e2;box-shadow:0 24px 80px rgba(15,23,42,.28);padding:18px;";
  const heading = document.createElement("h2");
  heading.textContent = title.slice(0, 80);
  heading.style.cssText = "font-size:18px;line-height:1.25;margin:0 0 12px;font-weight:700;";
  const body = document.createElement("div");
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "OK";
  close.style.cssText = "margin-top:14px;border:1px solid #0f766e;border-radius:6px;background:#0f766e;color:#fff;padding:9px 14px;cursor:pointer;";
  close.onclick = () => overlay.remove();
  panel.append(heading, body, close);
  overlay.append(panel);
  document.body.append(overlay);
  return { overlay, body, close };
}

function showSupportMessage(title: string, message: string) {
  const modal = supportOverlayBase(title || "Support message");
  const text = document.createElement("p");
  text.textContent = message.slice(0, 1000);
  text.style.cssText = "white-space:pre-wrap;line-height:1.45;margin:0;";
  modal.body.append(text);
  return new Promise<boolean>((resolve) => {
    modal.close.onclick = () => {
      modal.overlay.remove();
      resolve(true);
    };
  });
}

function showSupportImage(title: string, imageUrl: string, caption?: string) {
  const modal = supportOverlayBase(title || "Support image");
  const image = document.createElement("img");
  image.src = imageUrl;
  image.alt = caption || "Support-provided image";
  image.style.cssText = "display:block;max-width:100%;height:auto;border-radius:8px;border:1px solid #e5e7eb;";
  modal.body.append(image);
  if (caption) {
    const captionEl = document.createElement("p");
    captionEl.textContent = caption.slice(0, 300);
    captionEl.style.cssText = "line-height:1.4;margin:10px 0 0;color:#475569;";
    modal.body.append(captionEl);
  }
  return new Promise<boolean>((resolve) => {
    modal.close.onclick = () => {
      modal.overlay.remove();
      resolve(true);
    };
  });
}

function showSupportIframe(title: string, frameUrl: string) {
  const modal = supportOverlayBase(title || "Support page");
  const notice = document.createElement("p");
  notice.textContent = "Support opened an approved page here. This page remains connected to support.";
  notice.style.cssText = "line-height:1.4;margin:0 0 10px;color:#475569;";
  const frame = document.createElement("iframe");
  frame.src = frameUrl;
  frame.title = title.slice(0, 80);
  frame.sandbox.add("allow-forms", "allow-scripts", "allow-popups");
  frame.referrerPolicy = "strict-origin-when-cross-origin";
  frame.style.cssText = "display:block;width:min(960px,82vw);height:min(680px,72vh);border:1px solid #d5d9e2;border-radius:8px;background:#fff;";
  modal.body.append(notice, frame);
  return new Promise<boolean>((resolve) => {
    modal.close.textContent = "Close frame";
    modal.close.onclick = () => {
      modal.overlay.remove();
      resolve(true);
    };
  });
}

async function measureApiLatency(samples: number) {
  const timings: number[] = [];
  for (let index = 0; index < samples; index += 1) {
    const started = performance.now();
    await fetch(endpoint("/healthz"), { method: "GET", credentials: "omit", cache: "no-store" });
    timings.push(Math.round(performance.now() - started));
  }
  return { samples: timings, average_ms: Math.round(timings.reduce((sum, value) => sum + value, 0) / timings.length) };
}

async function handleAction(action: { action_id: string; type: string; parameters?: Record<string, unknown>; user_visible_description: string; expires_at?: string }) {
  if (action.expires_at && Date.parse(action.expires_at) < Date.now()) return;
  const params = action.parameters || {};
  const complete = (result: Record<string, unknown>) => post(`/api/actions/${action.action_id}/result`, scrubPayload(result));
  try {
    switch (action.type) {
      case "REFRESH_BROWSER_INFORMATION":
      case "CHECK_SUPPORTED_BROWSER_APIS":
      case "RECALCULATE_VIEWPORT":
        await complete({ diagnostics: collectDiagnostics() });
        break;
      case "MEASURE_API_LATENCY":
        await complete(await measureApiLatency(Number(params.samples || 5)));
        break;
      case "MEASURE_WEBSOCKET_LATENCY":
        socket?.send(JSON.stringify({ type: "pong", at: Date.now(), action_id: action.action_id }));
        await complete({ websocket_ready_state: socket?.readyState, connected: socket?.readyState === WebSocket.OPEN });
        break;
      case "COLLECT_PERFORMANCE_METRICS":
        await complete({ performance: performanceSnapshot, navigation: performance.getEntriesByType("navigation").slice(0, 1) });
        break;
      case "VERIFY_SDK_VERSION":
        await complete({ sdk_version: SDK_VERSION, app_version: options?.appVersion });
        break;
      case "REQUEST_RECONNECT":
        socket?.close();
        if (webSocketUrl) connectSocket(webSocketUrl);
        await complete({ reconnect_requested: true });
        break;
      case "DISPLAY_SUPPORT_NOTIFICATION":
        window.alert(String(params.message || action.user_visible_description).slice(0, 180));
        await complete({ displayed: true });
        break;
      case "DISPLAY_SUPPORT_MESSAGE": {
        const acknowledged = await showSupportMessage(String(params.title || "Support message"), String(params.message || ""));
        await complete({ displayed: true, acknowledged });
        break;
      }
      case "DISPLAY_SUPPORT_IMAGE": {
        const imageUrl = String(params.image_url || "");
        if (!urlIsDisplaySafe(imageUrl)) {
          await complete({ displayed: false, reason: "unsafe_image_url" });
          break;
        }
        const acknowledged = await showSupportImage(String(params.title || "Support image"), imageUrl, params.caption ? String(params.caption) : undefined);
        await complete({ displayed: true, acknowledged });
        break;
      }
      case "REQUEST_SUPPORT_USERNAME": {
        const promptText = String(params.prompt || action.user_visible_description).slice(0, 220);
        const username = window.prompt(promptText);
        if (username === null) {
          await complete({ prompted: true, accepted: false });
          break;
        }
        const trimmed = username.trim().slice(0, 80);
        if (!trimmed || isSensitiveInput(trimmed)) {
          window.alert("That value looks sensitive, so it was not sent to support.");
          await complete({ prompted: true, accepted: false, rejected: true, reason: "sensitive_or_empty_value" });
          break;
        }
        await complete({ prompted: true, accepted: true, username: trimmed });
        break;
      }
      case "ASK_REFRESH_PAGE": {
        const accepted = confirmAndRun("Support requested a page refresh.", () => location.reload());
        await complete({ prompted: true, accepted });
        break;
      }
      case "CLEAR_MONITORING_IDENTIFIER": {
        const accepted = confirmAndRun("Clear this page's monitoring identifier?", () => ClientMonitor.clearIdentity());
        await complete({ prompted: true, accepted });
        break;
      }
      case "OPEN_APPROVED_SUPPORT_PAGE": {
        const url = String(params.url || "");
        if (!supportUrlAllowed(url)) {
          await complete({ prompted: false, accepted: false, reason: "url_not_approved_by_client" });
          break;
        }
        const accepted = confirmAndRun("Open an approved support page?", () => window.open(url, "_blank", "noopener"));
        await complete({ prompted: true, accepted });
        break;
      }
      case "OPEN_APPROVED_SUPPORT_IFRAME": {
        const url = String(params.url || "");
        if (!urlIsDisplaySafe(url) || (options?.allowedSupportUrls?.length && !supportUrlAllowed(url))) {
          await complete({ displayed: false, reason: "url_not_approved_by_client" });
          break;
        }
        const acknowledged = await showSupportIframe(String(params.title || "Support page"), url);
        await complete({ displayed: true, acknowledged, kept_parent_session: true });
        break;
      }
      case "REQUEST_DIAGNOSTIC_LOG_UPLOAD": {
        if (!options?.diagnosticLogProvider) {
          await complete({ supported: false, reason: "diagnostic_log_provider_not_configured" });
          break;
        }
        const accepted = window.confirm("Upload approved diagnostic logs to support?");
        const logs = accepted ? await options.diagnosticLogProvider() : {};
        await complete({ prompted: true, accepted, logs: accepted ? logs : undefined });
        break;
      }
      case "RUN_APPLICATION_HEALTH_CHECK":
        await complete(options?.healthCheck ? await options.healthCheck() : { supported: false, reason: "health_check_not_configured" });
        break;
      default:
        await complete({ supported: false });
    }
  } catch (error) {
    await complete({ status: "FAILED", message: sanitizeErrorText(error) });
  }
}

export const ClientMonitor = {
  init(initOptions: InitOptions) {
    options = { ...defaultOptions, ...initOptions };
    sessionId = randomId("session");
    visitorId = storedVisitorId();
    consentState = initOptions.consent ? "GRANTED" : initOptions.consentMode === "implied" ? "IMPLIED" : "DENIED";
    installLifecycleListeners();
    installPerformanceCollection();
    installErrorCollection();
    if (consentState === "IMPLIED" || consentState === "GRANTED") {
      void register().then(() => emitSafeEvent("consent_granted", consentPayload()));
    }
  },
  setConsent(consent: boolean) {
    const previous = consentState;
    consentState = consent ? "GRANTED" : "WITHDRAWN";
    if (!consent) {
      void emitSafeEvent("consent_withdrawn", { previous });
      eventQueue.length = 0;
      registered = false;
      socket?.close();
      if (heartbeatTimer) window.clearInterval(heartbeatTimer);
      if (flushTimer) window.clearInterval(flushTimer);
      if (actionPollTimer) window.clearInterval(actionPollTimer);
      void post("/api/client/heartbeat", { session_id: sessionId, project_id: options?.projectId, state: "CONSENT_WITHDRAWN" }, true);
      return;
    }
    void register().then(() => emitSafeEvent("consent_granted", consentPayload()));
  },
  identify(reference: string) {
    if (sensitivePattern.test(reference) || /@|\+?\d[\d -]{7,}/.test(reference) || tokenLikePattern.test(reference)) {
      throw new Error("Sensitive identifiers are rejected by the monitoring SDK.");
    }
    return ClientMonitor.track("identity_reference_set", { reference });
  },
  track(name: string, payload: Record<string, unknown> = {}) {
    validateEvent(name, payload);
    return emitSafeEvent(name, payload);
  },
  refreshDiagnostics() {
    return emitSafeEvent("diagnostics_refreshed", collectDiagnostics());
  },
  getStatus() {
    return {
      sessionId,
      visitorId,
      consentState,
      state: currentState(),
      connected: socket?.readyState === WebSocket.OPEN,
      registered,
      queuedEvents: eventQueue.length,
      sdkVersion: SDK_VERSION
    };
  },
  clearIdentity() {
    storageRemove("clientMonitor.visitorId");
    visitorId = randomId("visitor");
    storageSet("clientMonitor.visitorId", visitorId);
  },
  disconnect() {
    registered = false;
    socket?.close();
    if (heartbeatTimer) window.clearInterval(heartbeatTimer);
    if (flushTimer) window.clearInterval(flushTimer);
    if (actionPollTimer) window.clearInterval(actionPollTimer);
  },
  destroy() {
    ClientMonitor.disconnect();
    cleanupCallbacks.splice(0).forEach((cleanup) => cleanup());
    installed = false;
  }
};

declare global {
  interface Window { ClientMonitor: typeof ClientMonitor; }
}

window.ClientMonitor = ClientMonitor;

const currentScript = document.currentScript as HTMLScriptElement | null;
if (currentScript?.dataset.projectId) {
  ClientMonitor.init({
    projectId: currentScript.dataset.projectId,
    endpoint: new URL(currentScript.src).origin,
    consentMode: (currentScript.dataset.consentMode as ConsentMode) || "explicit",
    consent: currentScript.dataset.consent === "true",
    collectPerformance: currentScript.dataset.collectPerformance !== "false",
    collectErrors: currentScript.dataset.collectErrors === "true",
    collectPageTitle: currentScript.dataset.collectPageTitle === "true"
  });
}
