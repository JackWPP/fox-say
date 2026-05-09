import { useState, useCallback, useEffect } from "react";
import { api } from "../../shared/api";
import type { CragAnswer, Citation, ConfidenceStatus } from "../../shared/types";
export type { ConfidenceStatus } from "../../shared/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  confidenceStatus?: ConfidenceStatus;
  refusalReason?: string;
}

export function useChat(courseId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<{
        messages: Array<{
          id: string;
          role: string;
          content: string;
          citations?: Citation[];
          confidence_status?: ConfidenceStatus;
          refusal_reason?: string;
        }>;
      }>(`/courses/${courseId}/chat/history`)
      .then((res) => {
        if (cancelled) return;
        setMessages(
          res.messages.map((m) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            citations: m.citations,
            confidenceStatus: m.confidence_status,
            refusalReason: m.refusal_reason,
          })),
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const sendQuestion = useCallback(
    async (question: string) => {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: question,
      };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);

      try {
        const answer = await api.post<CragAnswer>(`/courses/${courseId}/chat`, {
          question,
        });
        const aiMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: answer.answer,
          citations: answer.citations,
          confidenceStatus: answer.confidence_status,
          refusalReason: answer.refusal_reason,
        };
        setMessages((prev) => [...prev, aiMsg]);
      } catch {
        const errMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "哎呀，出了点问题，再试一次吧 🦊",
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        setLoading(false);
      }
    },
    [courseId],
  );

  return { messages, sendQuestion, loading };
}
