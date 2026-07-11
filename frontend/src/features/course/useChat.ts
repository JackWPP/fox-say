import { useState, useCallback, useEffect, useRef } from "react";
import { api } from "../../shared/api";
import { foxCopy } from "../../shared/fox-copy";
import type {
  AgentPhase,
  AnswerCitation,
  AnswerEnvelope,
  AnswerSource,
  ConfidenceStatus,
  SSEEvent,
  StreamEvent,
  TermHit,
  ToolCallState,
} from "../../shared/types";

export type { AgentPhase } from "../../shared/types";
export type { AnswerCitation, AnswerEnvelope } from "../../shared/types";
export type { ConfidenceStatus } from "../../shared/types";
export type { TermHit } from "../../shared/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** V2 envelope: server-assembled answer metadata + canonical citations. */
  envelope?: AnswerEnvelope | null;
  citations?: AnswerCitation[];
  /** Convenience mirrors of envelope fields, populated from history or done event. */
  runId?: string | null;
  sourceRevision?: string | null;
  knowledgeRevision?: string | null;
  confidenceStatus?: ConfidenceStatus | null;
  answerSource?: AnswerSource;
  /** Phase timeline recorded while streaming this message. */
  phases?: AgentPhase[];
  isStreaming?: boolean;
  isError?: boolean;
  /** Legacy compat (kept so older messages still render). */
  termHits?: TermHit[];
  toolCalls?: ToolCallState[];
  refusalReason?: string;
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

/**
 * Parse an SSE payload block of the form
 *   event: <type>
 *   data: <json>
 *
 *   event: <type>
 *   data: <json>
 *
 * Returns one event per completed `event:` line.  Lines with the same
 * `event:` are matched against the most recent `data:` line; some servers
 * emit multiple data lines per event which we treat as discarded fragments.
 */
function parseSseChunk(chunk: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  let currentType: string | null = null;
  for (const rawLine of chunk.split(/\r?\n/)) {
    if (!rawLine) continue;
    if (rawLine.startsWith(":")) {
      // SSE comment / heartbeat — ignore
      continue;
    }
    if (rawLine.startsWith("event:")) {
      currentType = rawLine.slice(6).trim();
      continue;
    }
    if (rawLine.startsWith("data:")) {
      const payload = rawLine.slice(5).trim();
      if (!currentType || !payload) continue;
      try {
        const data = JSON.parse(payload);
        events.push({ type: currentType, data } as SSEEvent);
      } catch {
        // Skip malformed frames; the next data line will be re-evaluated
        // against the next event: header on the next pass.
      }
      // Reset so a stray data line without an event header is ignored.
      currentType = null;
    }
  }
  return events;
}

export function useChat(courseId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [streamingBuffer, setStreamingBuffer] = useState("");
  const [activeToolCalls, setActiveToolCalls] = useState<ToolCallState[]>([]);
  /** Phases shown during streaming; cleared when streaming finishes. */
  const [activePhases, setActivePhases] = useState<AgentPhase[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);

  /** Ref to track which SSE run the current state belongs to. */
  const activeRunIdRef = useRef<string | null>(null);

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
        messages: Array<{
          id: string;
          role: string;
          content: string;
          citations?: AnswerCitation[];
          envelope?: AnswerEnvelope | null;
          confidence_status?: ConfidenceStatus | null;
          refusal_reason?: string;
          run_id?: string | null;
          source_revision?: string | null;
          knowledge_revision?: string | null;
          answer_source?: AnswerSource;
        }>;
        total: number;
        offset: number;
      }>(`/courses/${courseId}/chat/history?session_id=${sessionId}&limit=50&offset=0`);
      setMessages(
        data.messages.map((m) => {
          const envelope = m.envelope ?? null;
          const citations = m.citations ?? envelope?.citations ?? [];
          const confidence = (m.confidence_status
            ?? envelope?.confidence_status
            ?? null) as ConfidenceStatus | null;
          const answerSource = (m.answer_source
            ?? envelope?.answer_source
            ?? "supplementary") as AnswerSource;
          return {
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            envelope,
            citations,
            runId: m.run_id ?? null,
            sourceRevision: m.source_revision ?? null,
            knowledgeRevision: m.knowledge_revision ?? null,
            confidenceStatus: confidence,
            answerSource,
            refusalReason: m.refusal_reason,
          } satisfies ChatMessage;
        }),
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
    setActivePhases([]);
    activeRunIdRef.current = null;
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

  /**
   * Discards an incoming SSE event when it doesn't match the run we are
   * currently waiting on.  Without this fence, a late event from a previous
   * turn could overwrite the new run's buffer or phase list.
   */
  const isEventForActiveRun = useCallback((eventRunId: string | null | undefined) => {
    const active = activeRunIdRef.current;
    if (!active) return true;
    if (!eventRunId) return false;
    return eventRunId === active;
  }, []);

  const sendQuestion = useCallback(
    async (question: string, selectedSourceIds?: string[], selectedNoteIds?: string[]) => {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const sid = await createSession("新对话");
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
      setActivePhases([]);
      activeRunIdRef.current = null;

      let aiMsgId: string | null = null;
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
        let pendingEnvelope: AnswerEnvelope | null = null;
        let pendingCitations: AnswerCitation[] = [];
        let pendingRunId: string | null = null;
        let pendingSourceRevision: string | null = null;
        let pendingKnowledgeRevision: string | null = null;
        let pendingConfidence: ConfidenceStatus | null = null;
        let pendingAnswerSource: AnswerSource | undefined;
        const phases: AgentPhase[] = [];
        let streamError = false;
        let streamErrorMessage = "";

        const commitAssistant = () => {
          if (!aiMsgId) return;
          const id = aiMsgId;
          setMessages((prev) => prev.map((m) => (m.id === id
            ? {
                ...m,
                content: fullAnswer,
                envelope: pendingEnvelope,
                citations: pendingCitations,
                runId: pendingRunId,
                sourceRevision: pendingSourceRevision,
                knowledgeRevision: pendingKnowledgeRevision,
                confidenceStatus: pendingConfidence,
                answerSource: pendingAnswerSource,
                phases: [...phases],
                isStreaming: false,
                isError: streamError,
              }
            : m)));
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });

          // SSE blocks are terminated by a blank line.
          let cut = buf.indexOf("\n\n");
          while (cut >= 0) {
            const block = buf.slice(0, cut);
            buf = buf.slice(cut + 2);
            const events = parseSseChunk(block);
            for (const ev of events) {
              if (ev.type === "accepted") {
                // The very first event announces the run.  All further
                // events must carry a matching run_id.
                const incoming = ev.data.run_id;
                activeRunIdRef.current = incoming;
                pendingRunId = incoming;
                pendingSourceRevision = ev.data.source_revision ?? null;
                pendingKnowledgeRevision = ev.data.knowledge_revision ?? null;
                aiMsgId = aiMsgId ?? generateId();
                const provisional: ChatMessage = {
                  id: aiMsgId,
                  role: "assistant",
                  content: fullAnswer,
                  runId: incoming,
                  sourceRevision: pendingSourceRevision,
                  knowledgeRevision: pendingKnowledgeRevision,
                  phases: [],
                  isStreaming: true,
                };
                setMessages((prev) => (prev.some((m) => m.id === aiMsgId) ? prev : [...prev, provisional]));
                continue;
              }
              if (!isEventForActiveRun((ev.data as { run_id?: string }).run_id)) {
                continue;
              }
              if (ev.type === "phase") {
                const phaseEntry: AgentPhase = {
                  phase: ev.data.phase,
                  agent_role: ev.data.agent_role,
                  display_message: ev.data.display_message,
                };
                phases.push(phaseEntry);
                setActivePhases([...phases]);
                if (aiMsgId) {
                  const id = aiMsgId;
                  setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, phases: [...phases] } : m)));
                }
                continue;
              }
              if (ev.type === "token") {
                fullAnswer += ev.data.delta ?? "";
                setStreamingBuffer(fullAnswer);
                if (aiMsgId) {
                  const id = aiMsgId;
                  setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content: fullAnswer } : m)));
                }
                continue;
              }
              if (ev.type === "done") {
                if (ev.data.answer) {
                  fullAnswer = ev.data.answer;
                }
                pendingEnvelope = ev.data.envelope ?? null;
                pendingCitations = ev.data.citations ?? [];
                pendingConfidence = (ev.data.confidence_status ?? null) as ConfidenceStatus | null;
                pendingAnswerSource = ev.data.answer_source;
                if (pendingEnvelope) {
                  if (pendingCitations.length === 0) {
                    pendingCitations = pendingEnvelope.citations ?? [];
                  }
                  if (pendingConfidence == null) {
                    pendingConfidence = pendingEnvelope.confidence_status;
                  }
                  if (!pendingAnswerSource) {
                    pendingAnswerSource = pendingEnvelope.answer_source;
                  }
                  if (pendingSourceRevision === null) {
                    pendingSourceRevision = pendingEnvelope.source_revision;
                  }
                  if (pendingKnowledgeRevision === null) {
                    pendingKnowledgeRevision = pendingEnvelope.knowledge_revision;
                  }
                }
                continue;
              }
              if (ev.type === "error") {
                fullAnswer = ev.data.message || foxCopy.errors.generic;
                streamError = true;
                streamErrorMessage = ev.data.message;
                continue;
              }
              // Unknown event types are intentionally ignored — the SSE
              // envelope is the source of truth, not the event name set.
              // Legacy `tool_call` events would also fall through here.
            }
            cut = buf.indexOf("\n\n");
          }
        }

        if (!aiMsgId) {
          // Server never emitted `accepted` — synthesise an error message
          // so the user sees something rather than a silent empty bubble.
          aiMsgId = generateId();
          setMessages((prev) => [...prev, {
            id: aiMsgId as string,
            role: "assistant",
            content: streamErrorMessage || foxCopy.errors.generic,
            isError: !streamErrorMessage,
            isStreaming: false,
          }]);
        } else {
          commitAssistant();
        }
        setStreamingBuffer("");
        setActiveToolCalls([]);
        setActivePhases([]);
        activeRunIdRef.current = null;
        loadSessions(); // refresh session list (updated_at)
      } catch {
        const errMsg: ChatMessage = {
          id: generateId(),
          role: "assistant",
          content: foxCopy.errors.generic,
          isError: true,
        };
        setMessages((prev) => [...prev, errMsg]);
        setStreamingBuffer("");
        setActiveToolCalls([]);
        setActivePhases([]);
        activeRunIdRef.current = null;
      } finally {
        setLoading(false);
      }
    },
    [courseId, activeSessionId, createSession, loadSessions, isEventForActiveRun],
  );

  return {
    messages,
    sendQuestion,
    loading,
    streamingBuffer,
    activeToolCalls,
    activePhases,
    sessions,
    activeSessionId,
    switchSession,
    createSession,
    deleteSession,
  };
}

/**
 * Helper used by other components to decide which answer surface to render
 * from a V2 envelope or fallback message fields.
 */
export function deriveAnswerState(message: ChatMessage): {
  availability: "available" | "unavailable";
  confidenceStatus: ConfidenceStatus | null;
  answerSource: AnswerSource;
  isMaterial: boolean;
  isSupplementary: boolean;
  isUnavailable: boolean;
} {
  const envelope = message.envelope ?? null;
  const availability = envelope?.retrieval_availability ?? (message.isError ? "unavailable" : "available");
  const confidenceStatus = (envelope?.confidence_status
    ?? message.confidenceStatus
    ?? null) as ConfidenceStatus | null;
  const answerSource = (envelope?.answer_source
    ?? message.answerSource
    ?? "supplementary") as AnswerSource;
  return {
    availability,
    confidenceStatus,
    answerSource,
    isMaterial: availability === "available" && answerSource === "material",
    isSupplementary: availability === "available" && answerSource === "supplementary",
    isUnavailable: availability === "unavailable",
  };
}