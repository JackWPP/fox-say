/**
 * Virtual display screen — default: AI chat. Tab to switch to quiz mode.
 * Calls GET /dashboard (polled every 30s) + POST /courses/{id}/quiz (on demand).
 */
import { useState, useEffect, useCallback, useRef, KeyboardEvent } from "react";
import { api } from "../../shared/api";
import { useChat } from "../course/useChat";
import {
  Loader2, RefreshCw, ChevronRight, ChevronLeft, Eye, EyeOff,
  Zap, CheckCircle2, AlertCircle, FileText, Power, MessageCircle,
  Send, Sparkles,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface DashboardCourse {
  id: string; title: string; icon: string; status: string;
  teacher: string | null; exam_date: string | null;
  days_left: number | null; material_count: number; summary: string;
}
interface DashboardStats {
  total_courses: number; ready_courses: number;
  nearest_exam: { course_id: string; title: string; icon: string; days_left: number } | null;
}
interface QuizQuestion {
  id: string; type: "choice" | "fill" | "proof";
  kc_id: string; kc_name: string; question: string;
  options?: string[]; answer: string; explanation: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function padTwo(n: number) { return String(n).padStart(2, "0"); }
function formatClock(d: Date) {
  return `${padTwo(d.getHours())}:${padTwo(d.getMinutes())}:${padTwo(d.getSeconds())}`;
}
function formatDate(d: Date) {
  const days = ["日","一","二","三","四","五","六"];
  return `${d.getFullYear()}-${padTwo(d.getMonth()+1)}-${padTwo(d.getDate())} 周${days[d.getDay()]}`;
}

const STATUS_CFG: Record<string, { dot: string; label: string }> = {
  empty:      { dot: "bg-slate-500",   label: "未上传" },
  processing: { dot: "bg-amber-400",   label: "处理中" },
  ready:      { dot: "bg-emerald-400", label: "就绪"   },
  failed:     { dot: "bg-red-500",     label: "出错"   },
};

// ─── GlassPanel ───────────────────────────────────────────────────────────────

function GlassPanel({ children, className="" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white/5 border border-white/10 rounded-2xl backdrop-blur-sm ${className}`}>
      {children}
    </div>
  );
}

// ─── Chat panel ───────────────────────────────────────────────────────────────

function ChatPanel({ courseId }: { courseId: string }) {
  const { messages, sendQuestion, loading, streamingBuffer, activeToolCalls } = useChat(courseId);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingBuffer, activeToolCalls]);

  function handleSend() {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    sendQuestion(q);
  }
  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  const SUGGESTIONS = [
    "这门课最核心的概念是什么？",
    "帮我梳理一下知识体系",
    "我应该从哪里开始复习？",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3 fox-scroll min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 pb-4">
            <span className="text-4xl select-none fox-breathe inline-block">🦊</span>
            <p className="text-white/30 text-sm">问狐狸任何关于这门课的问题</p>
            <div className="flex flex-wrap gap-2 justify-center mt-1">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => sendQuestion(s)}
                  className="px-3 py-1.5 rounded-full text-xs bg-white/8 border border-white/12 text-white/50
                    hover:bg-foxAmber/15 hover:border-foxAmber/30 hover:text-amber-200 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start gap-2"}`}>
            {msg.role === "assistant" && (
              <div className="shrink-0 w-7 h-7 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-sm mt-0.5">
                🦊
              </div>
            )}
            <div className={`max-w-[78%] rounded-2xl px-3 py-2 text-xs leading-relaxed
              ${msg.role === "user"
                ? "bg-gradient-to-br from-foxAmber to-orange-400 text-white rounded-br-sm"
                : "bg-white/8 border border-white/10 text-white/80 rounded-bl-sm"
              }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {/* Tool call indicator */}
        {activeToolCalls.length > 0 && (
          <div className="flex justify-start gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-sm shrink-0">🦊</div>
            <div className="bg-white/8 border border-white/10 rounded-2xl rounded-bl-sm px-3 py-2 text-xs text-foxAmber flex items-center gap-1.5">
              <div className="flex gap-0.5">
                {[0,150,300].map(d => (
                  <div key={d} className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
              正在查阅材料…
            </div>
          </div>
        )}
        {/* Streaming */}
        {streamingBuffer && (
          <div className="flex justify-start gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-sm shrink-0">🦊</div>
            <div className="max-w-[78%] bg-white/8 border border-white/10 rounded-2xl rounded-bl-sm px-3 py-2 text-xs text-white/80 leading-relaxed">
              {streamingBuffer}
              <span className="inline-block w-1 h-3 bg-foxAmber ml-0.5 animate-pulse" />
            </div>
          </div>
        )}
        {loading && !streamingBuffer && activeToolCalls.length === 0 && (
          <div className="flex justify-start gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-sm shrink-0">🦊</div>
            <div className="bg-white/8 border border-white/10 rounded-2xl rounded-bl-sm px-3 py-2">
              <div className="flex gap-1">
                {[0,150,300].map(d => (
                  <div key={d} className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 px-3 pb-3 pt-2 border-t border-white/8">
        <div className="flex items-center gap-2 bg-white/8 border border-white/15 rounded-xl px-3 py-2
          focus-within:border-foxAmber/40 transition-colors">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="问这门课的任何问题…"
            className="flex-1 bg-transparent text-white/80 text-xs placeholder:text-white/25 outline-none"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="w-6 h-6 rounded-lg bg-foxAmber/80 hover:bg-foxAmber disabled:opacity-30 flex items-center justify-center transition-all"
          >
            <Send className="w-3 h-3 text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Quiz panel ───────────────────────────────────────────────────────────────

function QuizPanel({ courseId }: { courseId: string }) {
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [quizIdx, setQuizIdx] = useState(0);
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const loadedFor = useRef<string | null>(null);

  const loadQuiz = useCallback(async () => {
    setQuizLoading(true);
    setQuizError(null);
    // 不清空旧题 — 先保持旧题可见，新题回来后再替换
    try {
      const data = await api.post<{ questions: QuizQuestion[] }>(`/courses/${courseId}/quiz`, {
        count: 6, type: "mixed",
      });
      if (data.questions.length > 0) {
        setQuestions(data.questions);
        setQuizIdx(0);
        setSelected(null);
        setRevealed(false);
        loadedFor.current = courseId;
      } else {
        setQuizError("LLM 未能生成题目，请重试");
      }
    } catch (e) {
      setQuizError(e instanceof Error ? e.message : "出题失败");
    } finally {
      setQuizLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    if (loadedFor.current !== courseId) loadQuiz();
  }, [courseId, loadQuiz]);

  function next() { setQuizIdx(i => (i+1) % questions.length); setSelected(null); setRevealed(false); }
  function prev() { setQuizIdx(i => (i-1+questions.length) % questions.length); setSelected(null); setRevealed(false); }

  const q = questions[quizIdx] ?? null;

  if (quizError) return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3">
      <AlertCircle className="w-5 h-5 text-red-400" />
      <p className="text-red-400/70 text-xs">{quizError}</p>
      <button onClick={loadQuiz} className="text-white/40 hover:text-white/70 text-xs flex items-center gap-1">
        <RefreshCw className="w-3 h-3" /> 重试
      </button>
    </div>
  );

  if (!q) return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3">
      <Loader2 className="w-6 h-6 text-foxAmber animate-spin" />
      <p className="text-white/30 text-sm">正在出题中…</p>
    </div>
  );

  return (
    <div className="flex flex-col h-full p-4 gap-3 relative">
      {/* Loading bar — 换题时显示在顶部，不遮挡旧题 */}
      {quizLoading && (
        <div className="absolute top-0 left-0 right-0 h-0.5 overflow-hidden rounded-t-2xl">
          <div className="h-full bg-foxAmber animate-[shimmer_1.2s_ease-in-out_infinite]
            bg-gradient-to-r from-transparent via-foxAmber to-transparent bg-[length:200%_100%]" />
        </div>
      )}
      {/* Type badge + counter */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[0.6rem] font-bold uppercase tracking-wider
            ${q.type === "choice" ? "bg-blue-500/20 text-blue-300"
              : q.type === "fill" ? "bg-violet-500/20 text-violet-300"
              : "bg-orange-500/20 text-orange-300"}`}>
            {q.type === "choice" ? "选择题" : q.type === "fill" ? "填空题" : "简答题"}
          </span>
          <span className="text-white/25 text-[0.6rem]">{q.kc_name}</span>
        </div>
        <span className="text-white/25 text-xs tabular-nums">{quizIdx+1}/{questions.length}</span>
      </div>

      {/* Question */}
      <p className="text-white/85 text-sm leading-relaxed font-medium shrink-0">{q.question}</p>

      {/* Options */}
      {q.type === "choice" && q.options && (
        <div className="grid grid-cols-2 gap-2 flex-1 content-start">
          {q.options.map((opt, i) => {
            const letter = ["A","B","C","D"][i];
            const isCorrect = revealed && q.answer === letter;
            const isWrong = revealed && selected === letter && q.answer !== letter;
            const isChosen = selected === letter;
            return (
              <button key={letter} onClick={() => !revealed && setSelected(letter)}
                className={`px-3 py-2 rounded-xl text-left text-xs transition-all border
                  ${isCorrect ? "bg-emerald-500/25 border-emerald-400/60 text-emerald-300"
                    : isWrong ? "bg-red-500/20 border-red-400/50 text-red-300"
                    : isChosen ? "bg-foxAmber/20 border-foxAmber/50 text-amber-200"
                    : "bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:border-white/20"}`}>
                <span className="font-bold mr-1.5 opacity-60">{letter}.</span>
                {opt.replace(/^[A-D]\.\s*/,"")}
              </button>
            );
          })}
        </div>
      )}

      {/* Fill/proof answer area */}
      {q.type !== "choice" && (
        <div className={`flex-1 rounded-xl border p-3 transition-all
          ${revealed ? "bg-emerald-500/10 border-emerald-400/30" : "bg-white/4 border-white/10"}`}>
          {revealed
            ? <p className="text-emerald-300 text-xs leading-relaxed">{q.answer}</p>
            : <p className="text-white/20 text-xs italic">点击「揭晓答案」查看参考答案</p>}
        </div>
      )}

      {/* Explanation */}
      {revealed && q.explanation && (
        <div className="bg-amber-500/8 border border-amber-400/15 rounded-xl p-3 shrink-0">
          <p className="text-amber-200/70 text-[0.7rem] leading-relaxed">💡 {q.explanation}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between shrink-0 mt-auto">
        <div className="flex gap-2">
          <button onClick={prev}
            className="w-7 h-7 rounded-lg bg-white/8 hover:bg-white/15 text-white/40 hover:text-white/70 flex items-center justify-center transition-all">
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button onClick={next}
            className="w-7 h-7 rounded-lg bg-white/8 hover:bg-white/15 text-white/40 hover:text-white/70 flex items-center justify-center transition-all">
            <ChevronRight className="w-4 h-4" />
          </button>
          <button onClick={loadQuiz} disabled={quizLoading}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white/8 hover:bg-white/15 text-white/40 hover:text-white/70 text-xs transition-all disabled:opacity-30">
            <RefreshCw className={`w-3 h-3 ${quizLoading ? "animate-spin" : ""}`} />
            换一批题
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setSelected(null); setRevealed(false); }}
            className="text-white/25 hover:text-white/50 text-xs transition-colors">重置</button>
          <button onClick={() => setRevealed(r => !r)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all
              ${revealed
                ? "bg-white/10 text-white/50 hover:bg-white/15"
                : "bg-foxAmber/90 hover:bg-foxAmber text-white shadow-[0_0_12px_rgba(245,158,11,0.4)]"}`}>
            {revealed ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            {revealed ? "隐藏答案" : "揭晓答案"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function DisplayScreen() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);

  const [powered, setPowered] = useState(true);
  const [mode, setMode] = useState<"chat" | "quiz">("chat");

  // Dashboard
  const [courses, setCourses] = useState<DashboardCourse[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [dashLoading, setDashLoading] = useState(true);

  const fetchDashboard = useCallback(async () => {
    try {
      const data = await api.get<{ courses: DashboardCourse[]; stats: DashboardStats }>("/dashboard");
      setCourses(data.courses);
      setStats(data.stats);
    } catch { /* ignore */ } finally { setDashLoading(false); }
  }, []);

  useEffect(() => {
    fetchDashboard();
    const t = setInterval(fetchDashboard, 30_000);
    return () => clearInterval(t);
  }, [fetchDashboard]);

  // Selected course
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");
  const readyCourses = courses.filter(c => c.status === "ready");

  useEffect(() => {
    if (!selectedCourseId && readyCourses.length > 0) {
      const nearestReady = stats?.nearest_exam
        ? readyCourses.find(c => c.id === stats.nearest_exam?.course_id)
        : null;
      setSelectedCourseId(nearestReady?.id ?? readyCourses[0].id);
    }
  }, [readyCourses.length, stats?.nearest_exam?.course_id]);

  const selectedCourse = courses.find(c => c.id === selectedCourseId);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex flex-col items-center justify-center p-8 gap-5">

      {/* Monitor bezel */}
      <div className="relative">
        <div className="bg-gradient-to-b from-slate-700 to-slate-800 rounded-[2.5rem] p-[14px]
          shadow-[0_40px_80px_rgba(0,0,0,0.7),_0_0_0_1px_rgba(255,255,255,0.06),_inset_0_1px_0_rgba(255,255,255,0.1)]">

          <div className="relative rounded-[1.75rem] overflow-hidden" style={{ width: 920, height: 552 }}>

            {/* Screen off */}
            {!powered && (
              <div className="absolute inset-0 bg-black flex items-center justify-center z-20">
                <div className="w-2 h-2 rounded-full bg-slate-700" />
              </div>
            )}

            <div className={`absolute inset-0 bg-[#080c14] transition-opacity duration-500 ${powered ? "opacity-100" : "opacity-0"}`}>
              {/* Scanlines */}
              <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(0,0,0,0.04)_2px,rgba(0,0,0,0.04)_4px)] pointer-events-none z-10" />
              {/* Glow */}
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,rgba(245,158,11,0.06),transparent_60%)] pointer-events-none" />

              <div className="relative h-full flex flex-col z-0 p-4 gap-3">

                {/* Header */}
                <div className="flex items-center justify-between px-1 shrink-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xl select-none">🦊</span>
                    <span className="text-white/90 font-bold text-sm">FoxSay</span>
                    <span className="text-white/20 mx-1">|</span>
                    <span className="text-white/40 text-xs">学习助手</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-white/40 text-xs tabular-nums">{formatDate(now)}</span>
                    <span className="text-foxAmber font-bold text-base tabular-nums tracking-widest">{formatClock(now)}</span>
                    <button onClick={fetchDashboard} className="text-white/25 hover:text-white/60 transition-colors">
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Main */}
                <div className="flex gap-3 flex-1 min-h-0">

                  {/* Left — course list */}
                  <div className="w-52 flex flex-col gap-2 shrink-0">
                    {/* Nearest exam */}
                    {stats?.nearest_exam && (
                      <GlassPanel className="p-3 flex items-center gap-2.5 border-amber-400/20">
                        <span className="text-2xl select-none">{stats.nearest_exam.icon}</span>
                        <div className="flex-1 min-w-0">
                          <p className="text-white/40 text-[0.58rem] font-semibold uppercase tracking-wider">最近考试</p>
                          <p className="text-white/85 text-xs font-bold truncate">{stats.nearest_exam.title}</p>
                        </div>
                        <div className={`flex flex-col items-center shrink-0 ${stats.nearest_exam.days_left <= 3 ? "text-red-400" : stats.nearest_exam.days_left <= 7 ? "text-amber-400" : "text-emerald-400"}`}>
                          <span className="text-3xl font-black tabular-nums leading-none">{stats.nearest_exam.days_left}</span>
                          <span className="text-[0.55rem] opacity-70">天后</span>
                        </div>
                      </GlassPanel>
                    )}

                    {/* Courses */}
                    <GlassPanel className="flex-1 overflow-hidden flex flex-col">
                      <div className="px-3 pt-2.5 pb-1.5 border-b border-white/8 shrink-0">
                        <p className="text-white/35 text-[0.58rem] font-semibold uppercase tracking-wider">
                          课程 · {courses.length}
                        </p>
                      </div>
                      <div className="flex-1 overflow-y-auto px-2 py-1.5 space-y-0.5">
                        {dashLoading && <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 text-white/20 animate-spin" /></div>}
                        {courses.map(course => {
                          const cfg = STATUS_CFG[course.status] ?? STATUS_CFG.empty;
                          const isSel = course.id === selectedCourseId;
                          return (
                            <button key={course.id} onClick={() => setSelectedCourseId(course.id)}
                              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-left transition-all border
                                ${isSel ? "bg-foxAmber/15 border-foxAmber/25" : "hover:bg-white/5 border-transparent"}`}>
                              <span className="text-base select-none shrink-0">{course.icon}</span>
                              <div className="flex-1 min-w-0">
                                <p className={`text-xs font-medium truncate ${isSel ? "text-white/90" : "text-white/55"}`}>{course.title}</p>
                                <div className="flex items-center gap-1">
                                  <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                                  <span className="text-white/25 text-[0.55rem]">{cfg.label}</span>
                                  {course.days_left !== null && course.days_left >= 0 && (
                                    <span className={`text-[0.55rem] ml-auto ${course.days_left <= 7 ? "text-amber-400" : "text-white/20"}`}>
                                      {course.days_left}天
                                    </span>
                                  )}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </GlassPanel>

                    {/* Stats */}
                    {stats && (
                      <div className="flex gap-2 shrink-0">
                        <GlassPanel className="flex-1 p-2 text-center">
                          <p className="text-white/25 text-[0.55rem]">全部</p>
                          <p className="text-white/70 text-lg font-bold leading-tight">{stats.total_courses}</p>
                        </GlassPanel>
                        <GlassPanel className="flex-1 p-2 text-center">
                          <p className="text-white/25 text-[0.55rem]">就绪</p>
                          <p className="text-emerald-400 text-lg font-bold leading-tight">{stats.ready_courses}</p>
                        </GlassPanel>
                      </div>
                    )}
                  </div>

                  {/* Right — chat / quiz */}
                  <GlassPanel className="flex-1 flex flex-col overflow-hidden">
                    {/* Tab header */}
                    <div className="flex items-center gap-1 px-3 pt-2.5 pb-0 border-b border-white/8 shrink-0">
                      <button
                        onClick={() => setMode("chat")}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs font-semibold transition-all border-b-2
                          ${mode === "chat"
                            ? "text-foxAmber border-foxAmber"
                            : "text-white/35 border-transparent hover:text-white/55"}`}
                      >
                        <MessageCircle className="w-3.5 h-3.5" />
                        AI 对话
                      </button>
                      <button
                        onClick={() => setMode("quiz")}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs font-semibold transition-all border-b-2
                          ${mode === "quiz"
                            ? "text-foxAmber border-foxAmber"
                            : "text-white/35 border-transparent hover:text-white/55"}`}
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        出题
                      </button>
                      {selectedCourse && (
                        <span className="ml-auto text-white/25 text-[0.65rem] truncate max-w-[140px] pb-1.5">
                          {selectedCourse.icon} {selectedCourse.title}
                        </span>
                      )}
                    </div>

                    {/* Panel content */}
                    <div className="flex-1 min-h-0 flex flex-col">
                      {!selectedCourseId || (mode === "quiz" && readyCourses.length === 0) ? (
                        <div className="flex-1 flex flex-col items-center justify-center gap-2">
                          <span className="text-4xl select-none">📭</span>
                          <p className="text-white/30 text-sm">
                            {!selectedCourseId ? "请先在左侧选择课程" : "暂无就绪课程，上传材料后可出题"}
                          </p>
                        </div>
                      ) : mode === "chat" ? (
                        <ChatPanel key={selectedCourseId} courseId={selectedCourseId} />
                      ) : (
                        <QuizPanel key={selectedCourseId} courseId={selectedCourseId} />
                      )}
                    </div>
                  </GlassPanel>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Stand */}
        <div className="flex flex-col items-center mt-[-2px]">
          <div className="w-20 h-5 bg-gradient-to-b from-slate-700 to-slate-800 rounded-b-sm shadow-[0_4px_12px_rgba(0,0,0,0.4)]" />
          <div className="w-36 h-2 bg-slate-800 rounded-b-xl shadow-[0_4px_16px_rgba(0,0,0,0.5)]" />
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3">
        <button onClick={() => setPowered(p => !p)}
          className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all border
            ${powered
              ? "bg-white/8 border-white/15 text-white/50 hover:bg-white/12"
              : "bg-emerald-500/20 border-emerald-400/40 text-emerald-400"}`}>
          <Power className="w-3.5 h-3.5" />
          {powered ? "关闭屏幕" : "开启屏幕"}
        </button>
        <a href="/" className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium border
          bg-white/8 border-white/15 text-white/50 hover:text-white/70 hover:bg-white/12 transition-all">
          ← 主界面
        </a>
      </div>

      <p className="text-white/12 text-xs">虚拟显示屏演示 · 接口实测</p>
    </div>
  );
}
