import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../../shared/api";
import type { CourseSkeleton } from "../../shared/types";

const POLL_INTERVAL = 10_000;

export function useSkeleton(courseId: string) {
  const [skeleton, setSkeleton] = useState<CourseSkeleton | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSkeleton = useCallback(async () => {
    try {
      const data = await api.get<CourseSkeleton>(`/courses/${courseId}/skeleton`);
      setSkeleton(data);
      setNotFound(false);
      setError(null);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes("404")) {
        setNotFound(true);
        setSkeleton(null);
      } else {
        setError(e instanceof Error ? e.message : "Failed to fetch skeleton");
      }
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    setLoading(true);
    setNotFound(false);
    setError(null);
    setSkeleton(null);

    fetchSkeleton();

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchSkeleton]);

  useEffect(() => {
    if (notFound && !intervalRef.current) {
      intervalRef.current = setInterval(fetchSkeleton, POLL_INTERVAL);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [notFound, fetchSkeleton]);

  return { skeleton, loading, error, notFound, refetch: fetchSkeleton };
}
