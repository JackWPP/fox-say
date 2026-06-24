import { useState, useCallback, useEffect } from "react";
import { api } from "../../shared/api";
import type { ReviewPlan, BtwInterjection } from "../../shared/types";

export type ReviewStepType = "teach" | "quiz" | "review";

export function useReviewStep(courseId: string) {
  const [stepContent, setStepContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [stepType, setStepType] = useState<ReviewStepType>("teach");

  const generateStep = useCallback(
    async (currentDay: number, type: ReviewStepType) => {
      setLoading(true);
      setStepType(type);
      try {
        const data = await api.post<{ content: string }>(
          `/courses/${courseId}/review-session/generate-step`,
          { current_day: currentDay, step_type: type },
        );
        setStepContent(data.content);
      } catch {
        setStepContent(null);
      } finally {
        setLoading(false);
      }
    },
    [courseId],
  );

  return { stepContent, loading, stepType, generateStep, setStepContent };
}

export interface ReviewProgress {
  session_id: string | null;
  status: string;
  current_day: number;
  current_step: string | null;
  completed_steps: string[];
}

export function useReviewPlan(courseId: string) {
  const [plan, setPlan] = useState<ReviewPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generatePlan = useCallback(
    async (examDate?: string): Promise<ReviewPlan | null> => {
      setLoading(true);
      setError(null);
      try {
        const body = examDate ? { exam_date: examDate } : undefined;
        const data = await api.post<ReviewPlan>(
          `/courses/${courseId}/review-plan`,
          body
        );
        setPlan(data);
        return data;
      } catch (e) {
        setError(e instanceof Error ? e.message : "生成复习计划失败");
        return null;
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

export function useReviewSession(courseId: string) {
  const [progress, setProgress] = useState<ReviewProgress>({
    session_id: null,
    status: "not_started",
    current_day: 1,
    current_step: null,
    completed_steps: [],
  });
  const [sessionLoading, setSessionLoading] = useState(false);

  const fetchProgress = useCallback(async () => {
    try {
      const data = await api.get<ReviewProgress>(`/courses/${courseId}/review-session/progress`);
      setProgress(data);
    } catch {
      // Ignore errors, stay on current progress
    }
  }, [courseId]);

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  const startSession = useCallback(async () => {
    setSessionLoading(true);
    try {
      const data = await api.post<{ session_id: string; status: string; current_day: number }>(
        `/courses/${courseId}/review-session/start`,
      );
      setProgress((prev) => ({ ...prev, session_id: data.session_id, status: data.status, current_day: data.current_day }));
    } catch {
      // Ignore
    } finally {
      setSessionLoading(false);
    }
  }, [courseId]);

  const advanceStep = useCallback(async (dayIndex: number, stepId: string) => {
    try {
      const data = await api.post<ReviewProgress>(
        `/courses/${courseId}/review-session/advance`,
        { current_day: dayIndex, step_id: stepId },
      );
      setProgress(data);
    } catch {
      // Ignore
    }
  }, [courseId]);

  const completeSession = useCallback(async () => {
    try {
      await api.post(`/courses/${courseId}/review-session/complete`);
      setProgress((prev) => ({ ...prev, status: "completed" }));
    } catch {
      // Ignore
    }
  }, [courseId]);

  return { progress, sessionLoading, startSession, advanceStep, completeSession, fetchProgress };
}
