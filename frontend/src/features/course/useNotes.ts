import { useState, useEffect, useCallback } from "react";
import { api } from "../../shared/api";
import type { Note } from "../../shared/types";

export function useNotes(courseId: string) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNotes = useCallback(async () => {
    setError(null);
    try {
      const data = await api.get<Note[]>(`/courses/${courseId}/notes`);
      setNotes(data);
      return data;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch notes");
      return null;
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  const createNote = useCallback(async (title: string, content: string) => {
    try {
      const note = await api.post<Note>(`/courses/${courseId}/notes`, { title, content });
      setNotes((prev) => [note, ...prev]);
      return note;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create note");
      throw e;
    }
  }, [courseId]);

  const updateNote = useCallback(async (noteId: string, updates: { title?: string; content?: string }) => {
    try {
      const note = await api.patch<Note>(`/courses/${courseId}/notes/${noteId}`, updates);
      setNotes((prev) => prev.map((n) => (n.id === noteId ? note : n)));
      return note;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update note");
      throw e;
    }
  }, [courseId]);

  const deleteNote = useCallback(async (noteId: string) => {
    try {
      await api.del(`/courses/${courseId}/notes/${noteId}`);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete note");
      throw e;
    }
  }, [courseId]);

  return { notes, loading, error, refetch: fetchNotes, createNote, updateNote, deleteNote };
}
