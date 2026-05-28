import { ref } from "vue";

const SESSION_KEY = "normaldone_ui_session_id";

export function useSession(request) {
  const sessionId = ref(null);

  async function ensureSession() {
    const stored = localStorage.getItem(SESSION_KEY);
    const data = await request("POST", "/ui/api/session/ensure", {
      session_id: sessionId.value || stored || null,
    });
    sessionId.value = data.session_id;
    localStorage.setItem(SESSION_KEY, sessionId.value);
    return sessionId.value;
  }

  async function dropSession() {
    if (!sessionId.value) return;
    await request("POST", "/ui/api/session/drop", { session_id: sessionId.value });
    localStorage.removeItem(SESSION_KEY);
    sessionId.value = null;
  }

  async function resetRun() {
    await ensureSession();
    await request("POST", "/ui/api/session/reset", { session_id: sessionId.value });
  }

  return { sessionId, ensureSession, dropSession, resetRun };
}
