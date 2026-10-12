const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const SESSION_KEY = "kb_analytics_session_id";

function getSessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

type AnalyticsEvent = {
  event_name: string;
  knowledge_base_id?: string | null;
  generation_id?: string | null;
  mind_map_id?: string | null;
  properties?: Record<string, unknown>;
};

const buffer: Array<{
  session_id: string;
  event_name: string;
  knowledge_base_id: string | null;
  generation_id: string | null;
  mind_map_id: string | null;
  client_event_id: string;
  properties: Record<string, unknown>;
}> = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let currentToken: string | null = null;

export function setAnalyticsToken(token: string | null): void {
  currentToken = token;
}

export function trackEvent(event: AnalyticsEvent): void {
  const entry = {
    session_id: getSessionId(),
    event_name: event.event_name,
    knowledge_base_id: event.knowledge_base_id || null,
    generation_id: event.generation_id || null,
    mind_map_id: event.mind_map_id || null,
    client_event_id: crypto.randomUUID(),
    properties: event.properties || {},
  };
  buffer.push(entry);

  if (!flushTimer) {
    flushTimer = setTimeout(flush, 2000);
  }
  if (buffer.length >= 10) {
    flush();
  }
}

export function flush(): void {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (buffer.length === 0 || !currentToken) return;

  const events = buffer.splice(0, 50);
  const token = currentToken;

  fetch(`${apiBaseUrl}/api/analytics/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ events }),
  }).catch(() => {
    // Analytics failure must not block user workflow
  });
}
