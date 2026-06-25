import { useState, useCallback, useEffect } from "react";
import { BookOpen, Loader2, Sparkles, RotateCcw } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import CitationCard from "./CitationCard";
import type { Citation, CourseSkeletonChapter } from "../../shared/types";

interface LectureViewProps {
  courseId: string;
  chapters: CourseSkeletonChapter[];
}

const API_BASE = "/api";

function getSavedLecture(courseId: string, chapterId: string): { content: string; citations: Citation[] } | null {
  try {
    const raw = localStorage.getItem(`foxsay_lecture_${courseId}_${chapterId}`);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return null;
}

function saveLecture(courseId: string, chapterId: string, content: string, citations: Citation[]) {
  try {
    localStorage.setItem(`foxsay_lecture_${courseId}_${chapterId}`, JSON.stringify({ content, citations }));
  } catch { /* ignore */ }
}

async function streamChat(
  courseId: string,
  question: string,
  onToken: (token: string) => void,
  onDone: (answer: string, citations: Citation[]) => void,
  onError: (message: string) => void,
) {
  try {
    const res = await fetch(`${API_BASE}/courses/${courseId}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`Stream error: ${res.status}`);
    const reader = res.body?.getReader();
    if (!reader) throw new Error("No stream body");
    const decoder = new TextDecoder();
    let buf = "";
    let full = "";
    let cits: Citation[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === "token") {
            full += evt.token || "";
            onToken(full);
          } else if (evt.type === "done") {
            full = evt.answer || full;
            cits = evt.citations || [];
          } else if (evt.type === "error") {
            onError(evt.message || "生成失败");
            return;
          }
        } catch { /* skip malformed */ }
      }
    }
    onDone(full, cits);
  } catch (e) {
    onError(e instanceof Error ? e.message : "生成失败");
  }
}

export default function LectureView({ courseId, chapters }: LectureViewProps) {
  const [selectedId, setSelectedId] = useState(chapters[0]?.id || "");
  const [content, setContent] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load saved lecture when chapter changes
  useEffect(() => {
    if (!selectedId) return;
    const saved = getSavedLecture(courseId, selectedId);
    if (saved) {
      setContent(saved.content);
      setCitations(saved.citations);
    } else {
      setContent("");
      setCitations([]);
    }
    setError("");
  }, [courseId, selectedId]);

  const handleGenerate = useCallback(async () => {
    if (!selectedId) return;
    const ch = chapters.find((c) => c.id === selectedId);
    const label = ch?.title || selectedId;
    setLoading(true);
    setContent("");
    setCitations([]);
    setError("");
    await streamChat(
      courseId,
      `请为"${label}"这一章生成一份详细讲义。要求：\n1. 列出本章核心概念及其定义\n2. 给出关键公式（如有）\n3. 提供典型例题与解题思路\n4. 总结重点和常见易错点\n\n请基于课程材料回答，不要编造内容。`,
      (token) => setContent(token),
      (answer, cits) => {
        setContent(answer);
        setCitations(cits);
        saveLecture(courseId, selectedId, answer, cits);
      },
      (msg) => setError(msg),
    );
    setLoading(false);
  }, [courseId, selectedId, chapters]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          className="flex-1 min-w-0 px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-midnightCharcoal focus:outline-none focus:ring-2 focus:ring-foxAmber/40 focus:border-foxAmber transition-colors"
        >
          {chapters.map((ch) => (
            <option key={ch.id} value={ch.id}>
              {ch.title}
            </option>
          ))}
        </select>
        <button
          onClick={handleGenerate}
          disabled={loading || !selectedId}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-foxAmber text-midnightCharcoal text-sm font-semibold hover:bg-foxAmber/90 transition-colors disabled:opacity-50 shadow-sm whitespace-nowrap"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : content ? (
            <RotateCcw className="w-4 h-4" />
          ) : (
            <BookOpen className="w-4 h-4" />
          )}
          {content ? "重新生成" : "生成讲义"}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {(content || loading) && (
        <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          {loading && !content && (
            <div className="flex items-center gap-3 py-8 justify-center">
              <div className="w-5 h-5 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
              <span className="text-sm text-gray-400">小狐狸正在写讲义...</span>
            </div>
          )}
          {content && <MarkdownRenderer content={content} streaming={loading} light />}
        </div>
      )}

      {!loading && content && citations.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-100 px-5 py-3 shadow-sm">
          <div className="flex items-center gap-1.5 text-[0.68rem] text-gray-500 mb-2">
            <Sparkles className="w-3 h-3 text-foxAmber" />
            参考了 {citations.length} 处材料
          </div>
          <div className="flex flex-wrap gap-1.5">
            {citations.map((c, i) => (
              <CitationCard key={i} citation={c} index={i} />
            ))}
          </div>
        </div>
      )}

      {!content && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <BookOpen className="w-12 h-12 mb-3 opacity-40" />
          <p className="text-lg">选择章节，生成讲义</p>
          <p className="text-xs mt-2 text-gray-300">基于课程材料生成，包含核心概念、公式和例题</p>
        </div>
      )}
    </div>
  );
}
