import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../../shared/api";
import type { Material, CourseStatus } from "../../shared/types";

export function useMaterials(courseId: string) {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMaterials = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<Material[]>(`/courses/${courseId}/materials`);
      setMaterials(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch materials");
      return null;
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    let cancelled = false;

    const initialFetch = async () => {
      setLoading(true);
      const data = await fetchMaterials();
      if (cancelled) return;
      if (data && data.some((m) => m.status === "processing")) {
        startPolling();
      }
    };

    const startPolling = () => {
      if (intervalRef.current) return;
      intervalRef.current = setInterval(async () => {
        const data = await fetchMaterials();
        if (data && !data.some((m) => m.status === "processing")) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      }, 5000);
    };

    initialFetch();

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchMaterials]);

  return { materials, loading, error, refetch: fetchMaterials };
}

export function useUploadMaterial(courseId: string) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setProgress(0);
      setError(null);
      try {
        const formData = new FormData();
        formData.append("file", file);
        setProgress(30);
        const material = await api.upload<Material>(
          `/courses/${courseId}/materials`,
          formData
        );
        setProgress(100);
        return material;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to upload material";
        setError(msg);
        throw e;
      } finally {
        setUploading(false);
      }
    },
    [courseId]
  );

  return { upload, uploading, progress, error };
}

export function useMaterialProgress(courseId: string, materialId: string | null) {
  const [progress, setProgress] = useState<{
    material_id: string;
    current_step: string | null;
    steps: Array<{ step: string; status: string; detail: string | null }>;
  } | null>(null);

  useEffect(() => {
    if (!materialId) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const data = await api.get<{
          material_id: string;
          current_step: string | null;
          steps: Array<{ step: string; status: string; detail: string | null }>;
        }>(`/courses/${courseId}/materials/${materialId}/progress`);
        if (cancelled) return;
        setProgress(data);
        if (data.current_step === "completed" || data.current_step === "failed") {
          return;
        }
      } catch {
        if (cancelled) return;
      }
    };

    poll();
    const interval = setInterval(poll, 3000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [courseId, materialId]);

  return progress;
}

export function useMaterialStatus(courseId: string, materialId: string | null) {
  const [status, setStatus] = useState<CourseStatus>("processing");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!materialId) return;

    const poll = async () => {
      try {
        const data = await api.get<{ status: CourseStatus }>(
          `/courses/${courseId}/materials/${materialId}/status`
        );
        setStatus(data.status);
        if (data.status === "ready" || data.status === "failed") {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 3000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [courseId, materialId]);

  return status;
}
