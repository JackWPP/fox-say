import { useState, useCallback, useEffect } from "react";
import { api } from "../../shared/api";
import { foxCopy } from "../../shared/fox-copy";
import type { Citation, ConfidenceStatus, ToolCallState, StreamEvent } from "../../shared/types";
export type { ConfidenceStatus } from "../../shared/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  confidenceStatus?: ConfidenceStatus;
  refusalReason?: string;
  toolCalls?: ToolCallState[];
  isStreaming?: boolean;
  isError?: boolean;
}

export interface ChatSession {
  id: string;
  course_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

function generateId() {
  return crypto.randomUUID();
}

const API_BASE = "/api";

export function useChat(courseId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [streamingBuffer, setStreamingBuffer] = useState("");
  const [activeToolCalls, setActiveToolCalls] = useState<ToolCallState[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);

  const loadSessions = useCallback(async () => {
    try {
      const data = await api.get<{ sessions: ChatSession[] }>(`/courses/${courseId}/chat/sessions`);
      setSessions(data.sessions);
      if (!activeSessionId && data.sessions.length > 0) {
        setActiveSessionId(data.sessions[0].id);
      }
    } catch { /* ignore */ }
  }, [courseId, activeSessionId]);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  const loadHistory = useCallback(async (sessionId: string) => {
    try {
      const data = await api.get<{
        messages: Array<{ id: string; role: string; content: string; citations?: Citation[]; confidence_status?: ConfidenceStatus; refusal_reason?: string }>;
        total: number;
        offset: number;
      }>(`/courses/${courseId}/chat/history?session_id=${sessionId}&limit=50&offset=0`);
      setMessages(
        data.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          citations: m.citations,
          confidenceStatus: m.confidence_status,
          refusalReason: m.refusal_reason,
        })),
      );
      setHistoryTotal(data.total);
      setHistoryOffset(data.offset);
    } catch { /* ignore */ }
  }, [courseId]);

  useEffect(() => {
    if (activeSessionId) {
      loadHistory(activeSessionId);
    }
  }, [activeSessionId, loadHistory]);

  const switchSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
    setStreamingBuffer("");
    setActiveToolCalls([]);
  }, []);

  const createSession = useCallback(async (title: string) => {
    try {
      const data = await api.post<{ session_id: string; title: string }>(
        `/courses/${courseId}/chat/sessions`,
        { title },
      );
      await loadSessions();
      setActiveSessionId(data.session_id);
      return data.session_id;
    } catch { return null; }
  }, [courseId, loadSessions]);

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await api.del(`/courses/${courseId}/chat/sessions/${sessionId}`);
      await loadSessions();
      if (activeSessionId === sessionId) {
        const remaining = sessions.filter((s) => s.id !== sessionId);
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id);
        } else {
          setActiveSessionId("");
          setMessages([]);
        }
      }
    } catch { /* ignore */ }
  }, [courseId, activeSessionId, loadSessions, sessions]);

  const sendQuestion = useCallback(
    async (question: string, selectedSourceIds?: string[], selectedNoteIds?: string[]) => {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const sid = await createSession("New Chat");
        if (!sid) return;
        sessionId = sid;
      }

      const userMsg: ChatMessage = {
        id: generateId(),
        role: "user",
        content: question,
      };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);
      setStreamingBuffer("");
      setActiveToolCalls([]);

      try {
        const body: Record<string, unknown> = { question, session_id: sessionId };
        if (selectedSourceIds && selectedSourceIds.length > 0) {
          body.selected_source_ids = selectedSourceIds;
        }
        if (selectedNoteIds && selectedNoteIds.length > 0) {
          body.selected_note_ids = selectedNoteIds;
        }
        const res = await fetch(`${API_BASE}/courses/${courseId}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!res.ok) throw new Error(`Stream error: ${res.status}`);

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No stream body");

        const decoder = new TextDecoder();
        let buf = "";
        let fullAnswer = "";
        let allCitations: Citation[] = [];
        let streamError = false;
        const toolCallMap = new Map<string, ToolCallState>();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event: StreamEvent = JSON.parse(line.slice(6));
              if (event.type === "tool_call") {
                const tc: ToolCallState = { id: generateId(), tool: event.tool || "unknown", args: event.args || {}, status: "running" };
                toolCallMap.set(tc.tool, tc);
                setActiveToolCalls([...toolCallMap.values()]);
              } else if (event.type === "token") {
                fullAnswer += event.token || "";
                setStreamingBuffer(fullAnswer);
              } else if (event.type === "done") {
                fullAnswer = event.answer || fullAnswer;
                allCitations = event.citations || [];
                // Mark all tool calls as done
                for (const tc of toolCallMap.values()) { tc.status = "done"; }
                setActiveToolCalls([]);
              } else if (event.type === "error") {
                fullAnswer = event.message || foxCopy.errors.generic;
                streamError = true;
              }
            } catch { /* skip malformed */ }
          }
        }

        const aiMsg: ChatMessage = { id: generateId(), role: "assistant", content: fullAnswer || foxCopy.errors.generic, citations: allCitations, toolCalls: [...toolCallMap.values()], isStreaming: false, isError: streamError };
        setMessages((prev) => [...prev, aiMsg]);
        setStreamingBuffer("");
        setActiveToolCalls([]);
        loadSessions(); // refresh session list (updated_at)
      } catch {
        const errMsg: ChatMessage = { id: generateId(), role: "assistant", content: foxCopy.errors.generic, isError: true };
        setMessages((prev) => [...prev, errMsg]);
        setStreamingBuffer("");
        setActiveToolCalls([]);
      } finally {
        setLoading(false);
      }
    },
    [courseId, activeSessionId, createSession, loadSessions],
  );

  return { messages, sendQuestion, loading, streamingBuffer, activeToolCalls, sessions, activeSessionId, switchSession, createSession, deleteSession };
}
