import { useState, useCallback } from "react";
import {
  HelpCircle, CheckCircle2, XCircle, ChevronLeft, ChevronRight, Loader2, RotateCcw,
} from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import type { Citation, CourseSkeletonChapter } from "../../shared/types";

interface QuizViewProps {
  courseId: string;
  chapters: CourseSkeletonChapter[];
}

interface Question {
  id: number;
  type: "choice" | "fill" | "proof";
  question: string;
  options?: string[];
  answer: string;
  explanation: string;
}

const API_BASE = "/api";

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

function extractJson(text: string): unknown {
  let clean = text.trim();
  const fenceMatch = clean.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenceMatch) clean = fenceMatch[1].trim();
  const start = clean.indexOf("[");
  const end = clean.lastIndexOf("]");
  if (start !== -1 && end > start) {
    return JSON.parse(clean.slice(start, end + 1));
  }
  return JSON.parse(clean);
}

export default function QuizView({ courseId, chapters }: QuizViewProps) {
  const [selectedId, setSelectedId] = useState(chapters[0]?.id || "");
  const [count, setCount] = useState(5);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedAnswer, setSelectedAnswer] = useState("");
  const [showAnswer, setShowAnswer] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [streamingText, setStreamingText] = useState("");

  const handleGenerate = useCallback(async () => {
    if (!selectedId) return;
    const ch = chapters.find((c) => c.id === selectedId);
    const label = ch?.title || selectedId;
    setLoading(true);
    setQuestions([]);
    setCurrentIdx(0);
    setSelectedAnswer("");
    setShowAnswer(false);
    setError("");
    setStreamingText("");

    let finalAnswer = "";
    let streamError = "";
    await streamChat(
      courseId,
      `请为"${label}"这一章生成 ${count} 道练习题。要求：
1. 题型包含选择题和填空题
2. 每道题必须有答案和详细解析
3. 难度适中，覆盖本章核心知识点

请严格按以下 JSON 数组格式输出，不要输出任何其他文字：
[
  {
    "type": "choice",
    "question": "题目内容",
    "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
    "answer": "A",
    "explanation": "解析内容"
  },
  {
    "type": "fill",
    "question": "填空题内容 ____",
    "answer": "正确答案",
    "explanation": "解析内容"
  }
]`,
      (token) => {
        finalAnswer = token;
        setStreamingText(token);
      },
      (answer) => {
        finalAnswer = answer;
      },
      (msg) => { streamError = msg; setError(msg); },
    );

    if (!streamError && finalAnswer) {
      try {
        const parsed = extractJson(finalAnswer);
        if (Array.isArray(parsed)) {
          setQuestions(parsed.map((q, i) => ({ id: i + 1, ...q })));
        }
      } catch {
        setError("解析练习题失败，请重试");
      }
    }
    setStreamingText("");
    setLoading(false);
  }, [courseId, selectedId, count, chapters]);

  const current = questions[currentIdx];

  const handleCheck = useCallback(() => {
    setShowAnswer(true);
  }, []);

  const handleRetry = useCallback(() => {
    setSelectedAnswer("");
    setShowAnswer(false);
  }, []);

  const handlePrev = useCallback(() => {
    if (currentIdx > 0) {
      setCurrentIdx((i) => i - 1);
      setSelectedAnswer("");
      setShowAnswer(false);
    }
  }, [currentIdx]);

  const handleNext = useCallback(() => {
    if (currentIdx < questions.length - 1) {
      setCurrentIdx((i) => i + 1);
      setSelectedAnswer("");
      setShowAnswer(false);
    }
  }, [currentIdx, questions.length]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          className="flex-1 min-w-0 px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-midnightCharcoal focus:outline-none focus:ring-2 focus:ring-foxAmber/40 focus:border-foxAmber transition-colors"
        >
          {chapters.map((ch) => (
            <option key={ch.id} value={ch.id}>{ch.title}</option>
          ))}
        </select>
        <select
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-midnightCharcoal focus:outline-none focus:ring-2 focus:ring-foxAmber/40 focus:border-foxAmber transition-colors"
        >
          {[3, 5, 8, 10].map((n) => (
            <option key={n} value={n}>{n} 题</option>
          ))}
        </select>
        <button
          onClick={handleGenerate}
          disabled={loading || !selectedId}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-foxAmber text-midnightCharcoal text-sm font-semibold hover:bg-foxAmber/90 transition-colors disabled:opacity-50 shadow-sm whitespace-nowrap"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <HelpCircle className="w-4 h-4" />
          )}
          生成练习题
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {loading && !streamingText && (
        <div className="flex items-center gap-3 py-8 justify-center">
          <div className="w-5 h-5 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-400">小狐狸正在出题...</span>
        </div>
      )}

      {streamingText && (
        <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          <MarkdownRenderer content={streamingText} streaming />
        </div>
      )}

      {!loading && questions.length > 0 && current && (
        <div className="space-y-4 fox-fade-in">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-midnightCharcoal">
              第 {currentIdx + 1} / {questions.length} 题
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-foxAmber/10 text-foxAmber font-medium">
              {current.type === "choice" ? "选择题" : current.type === "fill" ? "填空题" : "证明题"}
            </span>
          </div>

          <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm space-y-4">
            <p className="text-sm text-midnightCharcoal font-medium leading-relaxed">
              {current.question}
            </p>

            {current.type === "choice" && current.options && (
              <div className="space-y-2">
                {current.options.map((opt) => {
                  const isSelected = selectedAnswer === opt;
                  const isCorrect = showAnswer && opt === current.answer;
                  const isWrong = showAnswer && isSelected && opt !== current.answer;
                  return (
                    <button
                      key={opt}
                      onClick={() => !showAnswer && setSelectedAnswer(opt)}
                      disabled={showAnswer}
                      className={`w-full text-left px-4 py-3 rounded-xl border text-sm transition-all ${
                        isCorrect
                          ? "bg-emerald-50 border-emerald-300 text-emerald-700"
                          : isWrong
                            ? "bg-red-50 border-red-300 text-red-700"
                            : isSelected
                              ? "bg-foxAmber/10 border-foxAmber/40 text-midnightCharcoal"
                              : "bg-gray-50 border-gray-200 text-gray-600 hover:border-foxAmber/30 hover:bg-foxAmber/5"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {isCorrect && <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />}
                        {isWrong && <XCircle className="w-4 h-4 text-red-500 shrink-0" />}
                        <span>{opt}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {current.type === "fill" && (
              <div className="space-y-2">
                <input
                  type="text"
                  value={selectedAnswer}
                  onChange={(e) => setSelectedAnswer(e.target.value)}
                  placeholder="输入你的答案"
                  disabled={showAnswer}
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm bg-gray-50 text-midnightCharcoal placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-foxAmber/40 focus:border-foxAmber transition-colors disabled:opacity-60"
                />
                {showAnswer && (
                  <div className={`px-4 py-2 rounded-lg text-sm ${
                    selectedAnswer.trim() === current.answer.trim()
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-red-50 text-red-700"
                  }`}>
                    正确答案：{current.answer}
                  </div>
                )}
              </div>
            )}

            {!showAnswer && (
              <button
                onClick={handleCheck}
                disabled={!selectedAnswer}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-foxAmber text-midnightCharcoal text-sm font-semibold hover:bg-foxAmber/90 transition-colors disabled:opacity-50 shadow-sm"
              >
                <CheckCircle2 className="w-4 h-4" />
                检查答案
              </button>
            )}

            {showAnswer && (
              <div className="space-y-3 fox-fade-in">
                <div className="bg-midnightCharcoal/[0.03] rounded-xl px-4 py-3 border border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 mb-1">解析</p>
                  <div className="text-sm text-gray-700 leading-relaxed">
                    <MarkdownRenderer content={current.explanation} />
                  </div>
                </div>
                <button
                  onClick={handleRetry}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 hover:text-foxAmber transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  重新作答
                </button>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between">
            <button
              onClick={handlePrev}
              disabled={currentIdx === 0}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-500 hover:text-midnightCharcoal transition-colors disabled:opacity-30"
            >
              <ChevronLeft className="w-4 h-4" />
              上一题
            </button>
            <span className="text-xs text-gray-400">
              {currentIdx + 1} / {questions.length}
            </span>
            <button
              onClick={handleNext}
              disabled={currentIdx >= questions.length - 1}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-500 hover:text-midnightCharcoal transition-colors disabled:opacity-30"
            >
              下一题
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {!loading && !error && questions.length === 0 && !streamingText && (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <HelpCircle className="w-12 h-12 mb-3 opacity-40" />
          <p className="text-lg">选择章节，生成练习题</p>
          <p className="text-xs mt-2 text-gray-300">基于课程材料出题，支持选择题和填空题</p>
        </div>
      )}
    </div>
  );
}
