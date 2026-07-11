import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { getKnowledgeStatus } from "../../shared/api";
import type { KnowledgeStatus } from "../../types/foxsay";

const SOURCE_PROCESSING_POLL_MS = 5_000;
const MAX_SOURCE_PROCESSING_POLLS = 60;

interface InFlightRefresh {
  courseId: string;
  requestId: number;
  promise: Promise<KnowledgeStatus | null>;
}

function hasProcessingSourceMaterial(snapshot: KnowledgeStatus | null): boolean {
  return Boolean(snapshot?.materials.some((material) => material.status === "processing"));
}

/**
 * Keeps the V2 knowledge snapshot fresh without treating SSE as durable
 * state. We fetch once on mount/course change, then use a bounded, serial
 * polling loop only while a source material remains processing.
 */
export function useKnowledgeStatus(courseId: string) {
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatus | null>(null);
  const [loading, setLoading] = useState(Boolean(courseId));
  const [error, setError] = useState<string | null>(null);
  const [autoRefreshPaused, setAutoRefreshPaused] = useState(false);
  const mountedRef = useRef(false);
  const currentCourseIdRef = useRef(courseId);
  const requestIdRef = useRef(0);
  const inFlightRefreshRef = useRef<InFlightRefresh | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Clear the prior course snapshot before the new course paints. The request
  // sequence fence separately prevents an old response from writing back.
  useLayoutEffect(() => {
    currentCourseIdRef.current = courseId;
    requestIdRef.current += 1;
    inFlightRefreshRef.current = null;
    setKnowledgeStatus(null);
    setError(null);
    setAutoRefreshPaused(false);
    setLoading(Boolean(courseId));
  }, [courseId]);

  const refresh = useCallback((): Promise<KnowledgeStatus | null> => {
    // An old SSE/poll closure can fire between a route change's layout phase
    // and passive-effect cleanup. Do not let it even start a request for the
    // previous course.
    if (currentCourseIdRef.current !== courseId) {
      return Promise.resolve(null);
    }

    if (!courseId) {
      const requestId = ++requestIdRef.current;
      if (mountedRef.current && requestId === requestIdRef.current) {
        setKnowledgeStatus(null);
        setError(null);
        setLoading(false);
      }
      return Promise.resolve(null);
    }

    const inFlight = inFlightRefreshRef.current;
    if (inFlight?.courseId === courseId) {
      return inFlight.promise;
    }

    const requestId = ++requestIdRef.current;
    if (mountedRef.current && requestId === requestIdRef.current) {
      setLoading(true);
      setError(null);
    }

    const request = (async (): Promise<KnowledgeStatus | null> => {
      try {
        const snapshot = await getKnowledgeStatus(courseId);
        if (mountedRef.current && requestId === requestIdRef.current) {
          setKnowledgeStatus(snapshot);
        }
        return snapshot;
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "无法读取材料证据状态";
        if (mountedRef.current && requestId === requestIdRef.current) {
          setError(message);
        }
        return null;
      } finally {
        if (mountedRef.current && requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    })();

    inFlightRefreshRef.current = { courseId, requestId, promise: request };
    void request.finally(() => {
      if (inFlightRefreshRef.current?.requestId === requestId) {
        inFlightRefreshRef.current = null;
      }
    });
    return request;
  }, [courseId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sourceProcessing = hasProcessingSourceMaterial(knowledgeStatus);

  useEffect(() => {
    if (!sourceProcessing) {
      setAutoRefreshPaused(false);
      return;
    }

    let cancelled = false;
    let timeoutId: number | undefined;
    let pollCount = 0;
    const pollingCourseId = courseId;
    setAutoRefreshPaused(false);

    const scheduleNext = () => {
      if (cancelled || currentCourseIdRef.current !== pollingCourseId) return;
      if (pollCount >= MAX_SOURCE_PROCESSING_POLLS) {
        setAutoRefreshPaused(true);
        return;
      }
      timeoutId = window.setTimeout(() => {
        void pollOnce();
      }, SOURCE_PROCESSING_POLL_MS);
    };

    const pollOnce = async () => {
      if (cancelled || currentCourseIdRef.current !== pollingCourseId) return;
      pollCount += 1;
      const snapshot = await refresh();
      if (cancelled || currentCourseIdRef.current !== pollingCourseId) return;

      // A failed status read does not fabricate completion. The last durable
      // snapshot still says processing, so retry within the same bounded loop.
      const stillProcessing = snapshot
        ? hasProcessingSourceMaterial(snapshot)
        : true;
      if (!stillProcessing) {
        setAutoRefreshPaused(false);
        return;
      }
      scheduleNext();
    };

    scheduleNext();
    return () => {
      cancelled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [courseId, refresh, sourceProcessing]);

  return { knowledgeStatus, loading, error, autoRefreshPaused, refresh };
}
