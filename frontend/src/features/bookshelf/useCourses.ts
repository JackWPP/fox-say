import { useState, useEffect, useCallback } from "react";
import { api } from "../../shared/api";
import type { Course } from "../../shared/types";

export function useCourses() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCourses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<Course[]>("/courses");
      setCourses(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch courses");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCourses();
  }, [fetchCourses]);

  return { courses, loading, error, refetch: fetchCourses };
}

export function useCreateCourse() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createCourse = useCallback(
    async (data: { title: string; teacher?: string; exam_date?: string; icon?: string }) => {
      setLoading(true);
      setError(null);
      try {
        const course = await api.post<Course>("/courses", data);
        return course;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to create course";
        setError(msg);
        throw e;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { createCourse, loading, error };
}

export function useUpdateCourse() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateCourse = useCallback(
    async (courseId: string, data: { title?: string; teacher?: string; exam_date?: string; icon?: string }) => {
      setLoading(true);
      setError(null);
      try {
        const course = await api.patch<import("../../shared/types").Course>(`/courses/${courseId}`, data);
        return course;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Failed to update course";
        setError(msg);
        throw e;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { updateCourse, loading, error };
}

export function useCourse(courseId: string) {
  const [course, setCourse] = useState<Course | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCourse = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<Course>(`/courses/${courseId}`);
      setCourse(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch course");
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    fetchCourse();
  }, [fetchCourse]);

  return { course, loading, error, refetch: fetchCourse };
}

export function useImportTimetable() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ imported: number; courses: Course[] } | null>(null);

  const importTimetable = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const data = await api.upload<{ imported: number; courses: Course[] }>(
        "/courses/import-timetable",
        formData
      );
      setResult(data);
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to import timetable";
      setError(msg);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  return { importTimetable, loading, error, result };
}
