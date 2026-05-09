import { useState, useCallback } from "react";
import { api } from "../../shared/api";
import type { ReviewPlan, BtwInterjection } from "../../shared/types";

export function useReviewPlan(courseId: string) {
  const [plan, setPlan] = useState<ReviewPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generatePlan = useCallback(
    async (examDate?: string) => {
      setLoading(true);
      setError(null);
      try {
        const body = examDate ? { exam_date: examDate } : undefined;
        const data = await api.post<ReviewPlan>(
          `/courses/${courseId}/review-plan`,
          body
        );
        setPlan(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "生成复习计划失败");
      } finally {
        setLoading(false);
      }
    },
    [courseId]
  );

  return { plan, loading, error, generatePlan };
}

export function useBtw(courseId: string) {
  const [btwAnswer, setBtwAnswer] = useState<BtwInterjection | null>(null);
  const [loading, setLoading] = useState(false);

  const askBtw = useCallback(
    async (question: string) => {
      setLoading(true);
      setBtwAnswer(null);
      try {
        const data = await api.post<BtwInterjection>(
          `/courses/${courseId}/btw`,
          { question }
        );
        setBtwAnswer(data);
      } catch {
        setBtwAnswer(null);
      } finally {
        setLoading(false);
      }
    },
    [courseId]
  );

  const clearBtw = useCallback(() => {
    setBtwAnswer(null);
  }, []);

  return { btwAnswer, askBtw, loading, clearBtw };
}
