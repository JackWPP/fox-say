import { useRef, useEffect, useState, useCallback } from "react";
import {
  MessageCircle, Plus, Trash2, ChevronDown, History, Sparkles, BookOpen, HelpCircle, ListChecks,
  Send, RefreshCw, ThumbsDown, ThumbsUp, Check, Copy, AlertTriangle, FileText, Loader2, RotateCcw, Bookmark, Zap
} from "lucide-react";
import { useChat } from "./useChat";
import { api } from "../../shared/api";
import MarkdownRenderer from "./MarkdownRenderer";
import CitationCard from "./CitationCard";
import type { ChapterWiki, Course } from "../../shared/types";

const SUGGESTED_QUESTIONS = [
  { text: "这门课最核心的概念是什么？", icon: BookOpen },
  { text: "帮我梳理章节之间的关系", icon: ListChecks },
  { text: "出一道题考我", icon: HelpCircle },
];

interface CourseIndexChapter {
  id: string;
  title: string;
  key_concepts: string[];
  importance: string;
}

interface CourseIndexData {
  course_id: string;
  course_name: string;
  core_topics: string[];
  chapters: CourseIndexChapter[];
}

interface ChatWorkspaceProps {
  courseId: string;
  courseTitle: string;
  course?: Course;
  sourceCount: number;
  selectedSourceIds: string[];
  selectedNoteIds: string[];
  prefillQuestion?: string;
  onPrefillConsumed?: () => void;
  onSwitchToMaterials?: () => void;
}

function CourseSummaryCard({ courseId, courseSummary, courseStatus, courseTitle, onSaveNote }: {
  courseId: string;
  courseSummary?: string;
  courseStatus?: string;
  courseTitle: string;
  onSaveNote: (title: string, content: string) => void;
}) {
  const [wikis, setWikis] = useState<ChapterWiki[] | null>(null);
  const [courseIndex, setCourseIndex] = useState<CourseIndexData | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const [liveSummary, setLiveSummary] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const fetchData = async () => {
      try {
        const [wikiData, indexData] = await Promise.allSettled([
          api.get<{ chapter_wikis: ChapterWiki[] }>(`/courses/${courseId}/chapter-wikis`),
          api.get<{ content: string }>(`/courses/${courseId}/course-index`),
        ]);
        if (cancelled) return;
        if (wikiData.status === "fulfilled") {
          setWikis(wikiData.value.chapter_wikis || []);
        } else {
          setWikis([]);
        }
        if (indexData.status === "fulfilled") {
          try {
            setCourseIndex(JSON.parse(indexData.value.content));
          } catch {
            setCourseIndex(null);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchData();
    return () => { cancelled = true; };
  }, [courseId]);

  useEffect(() => {
    setLiveSummary(courseSummary || "");
  }, [courseSummary]);

  const wikiFallbackSummary = wikis && wikis.length > 0
    ? wikis.map(w => w.overview).filter(Boolean).join(" ")
    : "";

  const displaySummary = liveSummary || wikiFallbackSummary;

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const data = await api.post<{ summary: string }>(`/courses/${courseId}/summary/regenerate`, {});
      setLiveSummary(data.summary);
    } catch {
      // error will be visible via network; keep UI graceful
    } finally {
      setRegenerating(false);
    }
  };

  const handleCopy = async () => {
    const text = displaySummary || buildStructuredSummary();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch { /* ignore */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleSave = () => {
    const text = displaySummary || buildStructuredSummary();
    if (!text) return;
    onSaveNote("课程概述", text);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  function buildStructuredSummary(): string {
    if (!courseIndex) return "";
    const name = courseIndex.course_name || courseTitle;
    const chapters = courseIndex.chapters.filter(c => c.title && c.title !== "(未分章)");
    const topics = courseIndex.core_topics.slice(0, 5);
    const parts: string[] = [];
    parts.push(`${name}共包含${chapters.length}个主要章节：${chapters.map(c => c.title).join("、")}。`);
    if (topics.length > 0) {
      parts.push(`核心主题围绕${topics.join("、")}展开。`);
    }
    parts.push("建议按章节顺序循序渐进学习，重点关注各章节之间的关联。");
    return parts.join("");
  }

  const hasContent = displaySummary || courseIndex;
  const isProcessing = courseStatus === "processing" || (loading && !hasContent);

  if (isProcessing) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 mb-6">
        <div className="flex items-center gap-2 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">狐狸正在整理课程概述...</span>
        </div>
      </div>
    );
  }

  if (!hasContent) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 mb-6 border-l-4 border-l-foxAmber">
        <div className="flex items-start gap-3">
          <div className="text-2xl">🦊</div>
          <div>
            <p className="text-sm text-slate-600 leading-relaxed">
              上传材料后狐狸会为你生成课程概述，帮你快速了解这门课的全貌～
            </p>
          </div>
        </div>
      </div>
    );
  }

  const chapters = courseIndex?.chapters.filter(c => c.title && c.title !== "(未分章)") || [];
  const coreTopics = courseIndex?.core_topics || [];
  const showStructuredFallback = !displaySummary && courseIndex;

  return (
    <div className="bg-white rounded-2xl shadow-soft border border-slate-100 p-5 mb-6 border-l-4 border-l-foxAmber fox-fade-in">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Sparkles className="w-4 h-4 text-foxAmber" />
          <span className="text-sm font-semibold text-midnightCharcoal">课程概述</span>
          {chapters.length > 0 && (
            <span className="text-xs text-slate-400">· {chapters.length} 个章节</span>
          )}
          {coreTopics.length > 0 && (
            <span className="text-xs text-slate-400">· {coreTopics.length} 个核心主题</span>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          <button
            onClick={handleRegenerate}
            disabled={regenerating || !courseIndex}
            className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-amber-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            title="重新生成概述"
          >
            {regenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleSave}
            className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-amber-50 transition-colors"
            title="保存到笔记"
          >
            {saved ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Bookmark className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={handleCopy}
            className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-amber-50 transition-colors"
            title="复制"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {displaySummary ? (
        <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{displaySummary}</p>
      ) : showStructuredFallback ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-700 leading-relaxed">{buildStructuredSummary()}</p>
          <div className="pt-2 border-t border-slate-100">
            <div className="flex flex-wrap gap-1.5 mb-2">
              {coreTopics.slice(0, 6).map((topic) => (
                <span key={topic} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-foxAmber/10 text-foxAmber font-medium">
                  {topic}
                </span>
              ))}
            </div>
            <div className="space-y-1 mt-2">
              {chapters.slice(0, 5).map((ch, i) => (
                <div key={ch.id} className="flex items-start gap-2 text-xs text-slate-600">
                  <span className={`shrink-0 w-4 h-4 rounded flex items-center justify-center text-[10px] font-bold mt-0.5 ${
                    ch.importance === "high" ? "bg-red-100 text-red-600" : ch.importance === "medium" ? "bg-foxAmber/15 text-foxAmber" : "bg-slate-100 text-slate-500"
                  }`}>{i + 1}</span>
                  <div>
                    <span className="font-medium text-slate-700">{ch.title}</span>
                    {ch.key_concepts.length > 0 && (
                      <span className="text-slate-400 ml-1">— {ch.key_concepts.slice(0, 3).join("、")}{ch.key_concepts.length > 3 ? "..." : ""}</span>
                    )}
                  </div>
                </div>
              ))}
              {chapters.length > 5 && (
                <p className="text-xs text-slate-400 pl-6">还有 {chapters.length - 5} 个章节...</p>
              )}
            </div>
          </div>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="inline-flex items-center gap-1.5 text-xs text-foxAmber hover:text-amber-700 font-medium transition-colors disabled:opacity-50"
          >
            <Zap className="w-3 h-3" />
            {regenerating ? "AI 正在生成概述..." : "让 AI 生成更详细的课程概述"}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function FoxAvatar({ streaming, error }: { streaming?: boolean; error?: boolean }) {
  return (
    <div
      className={`shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-base shadow-md select-none ${
        streaming ? "fox-breathe" : ""
      } ${error ? "ring-2 ring-red-400/50" : ""}`}
    >
      🦊
    </div>
  );
}

export default function ChatWorkspace({
  courseId, courseTitle, course, sourceCount, selectedSourceIds, selectedNoteIds,
  prefillQuestion, onPrefillConsumed, onSwitchToMaterials
}: ChatWorkspaceProps) {
  const {
    messages, sendQuestion, loading, streamingBuffer, activeToolCalls,
    sessions, activeSessionId, switchSession, createSession, deleteSession,
  } = useChat(courseId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showSessionList, setShowSessionList] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = inputValue.trim();
    if (!trimmed || loading) return;
    sendQuestion(trimmed, selectedSourceIds, selectedNoteIds);
    setInputValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [inputValue, loading, sendQuestion, selectedSourceIds, selectedNoteIds]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingBuffer, activeToolCalls]);

  useEffect(() => {
    if (prefillQuestion) {
      setInputValue(prefillQuestion);
      onPrefillConsumed?.();
      textareaRef.current?.focus();
    }
  }, [prefillQuestion, onPrefillConsumed]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
  const isFirstLoad = messages.length === 0 && !loading;

  const handleRegenerate = () => {
    if (lastUserMessage) sendQuestion(lastUserMessage.content, selectedSourceIds, selectedNoteIds);
  };

  const handleFeedback = (msgId: string, kind: "up" | "down") => {
    console.info("[feedback]", msgId, kind);
  };

  const handleCopyMessage = async (text: string) => {
    try { await navigator.clipboard.writeText(text); } catch { /* ignore */ }
  };

  const [noteSavedId, setNoteSavedId] = useState<string | null>(null);

  const handleSaveToNote = async (content: string) => {
    try {
      const title = content.slice(0, 30).replace(/[#*\n]/g, "").trim() || "Chat 笔记";
      const note = await api.post<{ id: string; title: string }>(
        `/courses/${courseId}/notes`,
        { title, content },
      );
      setNoteSavedId(note.id);
      setTimeout(() => setNoteSavedId(null), 2000);
    } catch (e) {
      console.error("Failed to save note:", e);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="h-12 px-4 flex items-center gap-2 border-b border-slate-100 shrink-0">
        <button
          onClick={() => setShowSessionList(!showSessionList)}
          className="flex items-center gap-1.5 flex-1 text-left text-sm font-medium text-midnightCharcoal hover:text-foxAmber transition-colors min-w-0"
        >
          <History className="w-4 h-4 shrink-0 text-slate-400" />
          <span className="truncate">{activeSession?.title || "新对话"}</span>
          <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-slate-400 transition-transform ${showSessionList ? "rotate-180" : ""}`} />
        </button>
        <button
          onClick={async () => { await createSession("新对话"); }}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-foxAmber transition-colors"
          title="新会话"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={() => { if (activeSessionId) deleteSession(activeSessionId); }}
          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-red-500 transition-colors"
          title="删除会话"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {showSessionList && (
        <div className="mx-4 mt-2 bg-white border border-slate-200 rounded-xl shadow-md max-h-52 overflow-y-auto fox-fade-in fox-scroll z-10">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => { switchSession(s.id); setShowSessionList(false); }}
              className={`w-full text-left px-3 py-2.5 text-sm transition-colors border-b border-slate-50 last:border-0 ${
                s.id === activeSessionId
                  ? "bg-foxAmber/10 text-foxAmber"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <div className="truncate font-medium">{s.title}</div>
              <div className="text-[0.7rem] text-slate-400 mt-0.5">{s.updated_at?.slice(0, 16).replace("T", " ")}</div>
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-slate-400">还没有会话,问个问题开始吧</div>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 py-6 fox-scroll">
        <div className="max-w-3xl mx-auto">
          {isFirstLoad ? (
            <div className="flex flex-col items-center justify-center min-h-[50vh] text-center">
              <div className="text-6xl mb-4 fox-breathe">🦊</div>
              <h2 className="text-2xl font-bold text-midnightCharcoal mb-1">{courseTitle}</h2>
              <p className="text-sm text-slate-500 mb-6">{sourceCount} 个来源</p>

              <CourseSummaryCard
                courseId={courseId}
                courseSummary={course?.summary}
                courseStatus={course?.status}
                courseTitle={courseTitle}
                onSaveNote={handleSaveToNote}
              />

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-2xl mb-6">
                {SUGGESTED_QUESTIONS.map((q, i) => {
                  const Icon = q.icon;
                  return (
                    <button
                      key={i}
                      onClick={() => sendQuestion(q.text, selectedSourceIds, selectedNoteIds)}
                      className="group flex items-center gap-2 text-left p-3.5 rounded-2xl bg-white border border-slate-200 hover:border-foxAmber/40 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
                    >
                      <Icon className="w-4 h-4 text-foxAmber shrink-0" />
                      <span className="text-sm text-slate-700 leading-snug">{q.text}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg, idx) => {
                const isLastAi = msg.role === "assistant" && idx === messages.length - 1;
                if (msg.role === "user") {
                  return (
                    <div key={msg.id} className="flex justify-end fox-fade-in group">
                      <div className="flex items-end gap-2 max-w-[70%]">
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => handleCopyMessage(msg.content)}
                            className="p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                            title="复制"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <div className="bg-slate-100 text-slate-800 rounded-2xl rounded-br-sm px-4 py-2.5 text-sm shadow-sm whitespace-pre-wrap break-words">
                          {msg.content}
                        </div>
                      </div>
                    </div>
                  );
                }

                const isError = msg.isError;
                const isRefusal = msg.confidenceStatus === "out_of_scope";
                return (
                  <div key={msg.id} className="flex justify-start gap-3 fox-fade-in group">
                    <FoxAvatar error={isError} />
                    <div className="min-w-0 max-w-[82%]">
                      <div
                        className={`rounded-2xl rounded-bl-sm px-5 py-4 text-sm shadow-soft border ${
                          isError
                            ? "bg-red-50 text-red-800 border-red-200"
                            : isRefusal
                              ? "bg-slate-50 text-slate-500 border-slate-200"
                              : "bg-white border-slate-100"
                        }`}
                      >
                        {isError && (
                          <div className="flex items-center gap-2 mb-3">
                            <AlertTriangle className="w-4 h-4 text-red-500" />
                            <span className="text-xs font-medium text-red-600">出错了</span>
                            <button
                              onClick={handleRegenerate}
                              className="ml-auto flex items-center gap-1 text-xs text-red-600 hover:text-red-700"
                            >
                              <RotateCcw className="w-3 h-3" /> 重试
                            </button>
                          </div>
                        )}

                        {isRefusal || isError ? (
                          <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                        ) : (
                          <MarkdownRenderer content={msg.content} ai />
                        )}

                        {msg.citations && msg.citations.length > 0 && !isError && !isRefusal && (
                          <div className="mt-4 pt-3 border-t border-slate-100">
                            <div className="flex flex-wrap gap-1.5">
                              {msg.citations.map((c, i) => (
                                <CitationCard key={i} citation={c} index={i} courseId={courseId} light />
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      {!isError && !isRefusal && (
                        <div className="flex items-center gap-0.5 mt-2 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => handleCopyMessage(msg.content)}
                            className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-slate-100 transition-colors"
                            title="复制"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleSaveToNote(msg.content)}
                            className={`p-1.5 rounded-md transition-colors ${
                              noteSavedId
                                ? "text-green-500 bg-green-50"
                                : "text-slate-400 hover:text-foxAmber hover:bg-slate-100"
                            }`}
                            title="保存到笔记"
                          >
                            {noteSavedId ? <Check className="w-3.5 h-3.5" /> : <Bookmark className="w-3.5 h-3.5" />}
                          </button>
                          {isLastAi && (
                            <button
                              onClick={handleRegenerate}
                              className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-slate-100 transition-colors"
                              title="重新生成"
                            >
                              <RefreshCw className="w-3.5 h-3.5" />
                            </button>
                          )}
                          <button
                            onClick={() => handleFeedback(msg.id, "up")}
                            className="p-1.5 rounded-md text-slate-400 hover:text-emerald-600 hover:bg-slate-100 transition-colors"
                            title="有帮助"
                          >
                            <ThumbsUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleFeedback(msg.id, "down")}
                            className="p-1.5 rounded-md text-slate-400 hover:text-red-500 hover:bg-slate-100 transition-colors"
                            title="没帮助"
                          >
                            <ThumbsDown className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {activeToolCalls.length > 0 && (
                <div className="flex justify-start gap-3">
                  <FoxAvatar streaming />
                  <div className="bg-slate-50 border border-slate-100 rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
                    <div className="flex items-center gap-2 text-slate-500">
                      <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                        <div className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                        <div className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                      </div>
                      <span>正在查阅课程材料…</span>
                    </div>
                  </div>
                </div>
              )}

              {streamingBuffer && (
                <div className="flex justify-start gap-3 fox-fade-in">
                  <FoxAvatar streaming />
                  <div className="min-w-0 max-w-[82%] rounded-2xl rounded-bl-sm px-5 py-4 text-sm shadow-soft border bg-white border-slate-100">
                    <MarkdownRenderer content={streamingBuffer} streaming ai />
                  </div>
                </div>
              )}

              {loading && !streamingBuffer && activeToolCalls.length === 0 && (
                <div className="flex justify-start gap-3 fox-fade-in">
                  <FoxAvatar streaming />
                  <div className="rounded-2xl rounded-bl-sm px-5 py-4 text-sm shadow-soft border bg-white border-slate-100">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <div className="px-6 pb-6 pt-2 bg-white shrink-0">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-3 bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-soft focus-within:border-foxAmber/50 focus-within:shadow-lg transition-all">
            <button
              onClick={onSwitchToMaterials}
              className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-foxAmber transition-colors shrink-0 pb-1"
            >
              <FileText className="w-4 h-4" />
              <span>{selectedSourceIds.length + selectedNoteIds.length} 个来源</span>
            </button>
            <textarea
              ref={textareaRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              placeholder={loading ? "狐狸还在想…" : "问点什么关于这门课的..."}
              rows={1}
              className="flex-1 resize-none text-sm text-midnightCharcoal placeholder-slate-400 focus:outline-none bg-transparent disabled:opacity-50"
              style={{ minHeight: "1.5rem", maxHeight: "150px" }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
              }}
            />
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || loading}
              className="p-2.5 rounded-xl bg-foxAmber text-midnightCharcoal hover:bg-amber-500 disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0 shadow-sm"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-center text-[0.7rem] text-slate-400 mt-2 flex items-center justify-center gap-1">
            <MessageCircle className="w-3 h-3" />
            狐狸只基于本课材料回答
          </p>
        </div>
      </div>
    </div>
  );
}
