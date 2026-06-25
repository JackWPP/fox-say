import { useRef, useEffect, useState, useCallback } from "react";
import {
  MessageCircle, Plus, Trash2, ChevronDown, History, Sparkles, BookOpen, HelpCircle, ListChecks,
  Send, RefreshCw, ThumbsDown, ThumbsUp, Check, Copy, AlertTriangle, FileText, Loader2, RotateCcw, Bookmark
} from "lucide-react";
import { useChat } from "./useChat";
import { api } from "../../shared/api";
import MarkdownRenderer from "./MarkdownRenderer";
import CitationCard from "./CitationCard";
import type { ChapterWiki } from "../../shared/types";

const SUGGESTED_QUESTIONS = [
  { text: "这门课最核心的概念是什么？", icon: BookOpen },
  { text: "帮我梳理章节之间的关系", icon: ListChecks },
  { text: "出一道题考我", icon: HelpCircle },
];

interface ChatWorkspaceProps {
  courseId: string;
  courseTitle: string;
  sourceCount: number;
  selectedSourceIds: string[];
  selectedNoteIds: string[];
  prefillQuestion?: string;
  onPrefillConsumed?: () => void;
  onSwitchToMaterials?: () => void;
}

function CourseSummaryCard({ courseId, onSaveNote }: { courseId: string; onSaveNote: (title: string, content: string) => void }) {
  const [wikis, setWikis] = useState<ChapterWiki[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchWikis = async () => {
      try {
        const data = await api.get<ChapterWiki[]>(`/courses/${courseId}/chapter-wikis`);
        if (!cancelled) setWikis(data);
      } catch {
        if (!cancelled) setWikis([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchWikis();
    return () => { cancelled = true; };
  }, [courseId]);

  const summary = wikis && wikis.length > 0
    ? wikis.map(w => w.overview).join(" ")
    : "";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(summary);
    } catch { /* ignore */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleSave = () => {
    onSaveNote("课程概述", summary);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (loading) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-5 mb-6">
        <div className="flex items-center gap-2 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">狐狸正在整理课程概述...</span>
        </div>
      </div>
    );
  }

  if (!wikis || wikis.length === 0) {
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

  return (
    <div className="bg-white rounded-2xl shadow-soft border border-slate-100 p-5 mb-6 border-l-4 border-l-foxAmber fox-fade-in">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-foxAmber" />
          <span className="text-sm font-semibold text-midnightCharcoal">课程概述</span>
        </div>
        <div className="flex items-center gap-1">
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
      <p className="text-sm text-slate-700 leading-relaxed">{summary}</p>
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
  courseId, courseTitle, sourceCount, selectedSourceIds, selectedNoteIds,
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

  const handleSaveToNote = (content: string) => {
    console.info("[save-to-note]", content.slice(0, 50));
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

              <CourseSummaryCard courseId={courseId} onSaveNote={handleSaveToNote} />

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
                            className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-slate-100 transition-colors"
                            title="保存到笔记"
                          >
                            <Bookmark className="w-3.5 h-3.5" />
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
