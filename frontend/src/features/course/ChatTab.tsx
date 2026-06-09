import { useRef, useEffect, useState } from "react";
import {
  MessageCircle, Plus, Trash2, ChevronDown, History, Sparkles, BookOpen, HelpCircle, ListChecks,
} from "lucide-react";
import { useChat } from "./useChat";
import { foxCopy } from "../../shared/fox-copy";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import MarkdownRenderer from "./MarkdownRenderer";

interface ChatTabProps {
  courseId: string;
  prefillQuestion?: string;
  onPrefillConsumed?: () => void;
}

const SUGGESTED_QUESTIONS: { icon: typeof Sparkles; text: string; tone: string }[] = [
  { icon: BookOpen,    text: "这门课最核心的几个概念是什么?",   tone: "from-amber-50 to-orange-50" },
  { icon: ListChecks,  text: "我应该按什么顺序学这些章节?",     tone: "from-rose-50 to-amber-50" },
  { icon: HelpCircle,  text: "出一道能考我的题目并讲解一下",     tone: "from-emerald-50 to-teal-50" },
  { icon: Sparkles,    text: "我的薄弱环节在哪里?怎么补?",      tone: "from-sky-50 to-indigo-50" },
];

export default function ChatTab({ courseId, prefillQuestion, onPrefillConsumed }: ChatTabProps) {
  const {
    messages, sendQuestion, loading, streamingBuffer, activeToolCalls,
    sessions, activeSessionId, switchSession, createSession, deleteSession,
  } = useChat(courseId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showSessionList, setShowSessionList] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingBuffer, activeToolCalls]);

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");

  const handleRegenerate = () => {
    if (lastUserMessage) sendQuestion(lastUserMessage.content);
  };

  const handleFeedback = (msgId: string, kind: "up" | "down") => {
    // Local-only acknowledgement. Wire to a real feedback endpoint later.
    // eslint-disable-next-line no-console
    console.info("[feedback]", msgId, kind);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)]">
      {/* Session bar */}
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-gray-100">
        <button
          onClick={() => setShowSessionList(!showSessionList)}
          className="flex items-center gap-1.5 flex-1 text-left text-sm font-medium text-midnightCharcoal hover:text-foxAmber transition-colors min-w-0"
        >
          <History className="w-4 h-4 shrink-0 text-gray-400" />
          <span className="truncate">{activeSession?.title || "新对话"}</span>
          <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-gray-400 transition-transform ${showSessionList ? "rotate-180" : ""}`} />
        </button>
        <button
          onClick={async () => { await createSession("新对话"); }}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-foxAmber transition-colors"
          title="新会话"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={() => { if (activeSessionId) deleteSession(activeSessionId); }}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-red-500 transition-colors"
          title="删除会话"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Session list dropdown */}
      {showSessionList && (
        <div className="mb-3 bg-white border border-gray-200 rounded-xl shadow-md max-h-52 overflow-y-auto fox-fade-in fox-scroll">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => { switchSession(s.id); setShowSessionList(false); }}
              className={`w-full text-left px-3 py-2.5 text-sm transition-colors border-b border-gray-50 last:border-0 ${
                s.id === activeSessionId
                  ? "bg-foxAmber/10 text-foxAmber"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <div className="truncate font-medium">{s.title}</div>
              <div className="text-[0.7rem] text-gray-400 mt-0.5">{s.updated_at?.slice(0, 16).replace("T", " ")}</div>
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-gray-400">还没有会话,问个问题开始吧</div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-1 py-2 fox-scroll">
        {messages.length === 0 ? (
          <EmptyState onPick={sendQuestion} />
        ) : (
          <div className="space-y-5">
            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onRegenerate={msg.id === messages[messages.length - 1].id ? handleRegenerate : undefined}
                onFeedback={msg.role === "assistant" ? (kind) => handleFeedback(msg.id, kind) : undefined}
              />
            ))}
            {activeToolCalls.length > 0 && (
              <div className="flex justify-start pl-10">
                <div className="bg-midnightCharcoal/60 border border-white/5 rounded-2xl rounded-bl-sm px-4 py-2.5 text-xs text-warmWhite/80">
                  <div className="flex items-center gap-1.5 text-foxAmber">
                    <div className="flex gap-0.5">
                      <div className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-1.5 h-1.5 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="ml-1">正在查阅课程材料…</span>
                  </div>
                </div>
              </div>
            )}
            {streamingBuffer && (
              <div className="flex justify-start gap-2 fox-fade-in">
                <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-base shadow-md fox-breathe">
                  🦊
                </div>
                <div className="min-w-0 max-w-[82%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm shadow-sm border bg-midnightCharcoal text-warmWhite border-white/5">
                  <MarkdownRenderer content={streamingBuffer} streaming />
                </div>
              </div>
            )}
            {loading && !streamingBuffer && activeToolCalls.length === 0 && (
              <div className="flex justify-start gap-2 fox-fade-in">
                <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-base shadow-md fox-breathe">
                  🦊
                </div>
                <div className="rounded-2xl rounded-bl-sm px-4 py-3 text-sm shadow-sm border bg-midnightCharcoal text-warmWhite border-white/5">
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

      <div className="pt-3 border-t border-gray-100">
        <ChatInput onSend={sendQuestion} loading={loading} prefill={prefillQuestion} onPrefillConsumed={onPrefillConsumed} />
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-2">
      <div className="relative">
        <div className="text-7xl mb-4 fox-breathe inline-block">🦊</div>
      </div>
      <h3 className="text-lg font-bold text-midnightCharcoal mb-1">{foxCopy.chat.empty}</h3>
      <p className="text-xs text-gray-400 mb-6">{foxCopy.chat.emptyHint}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-2xl">
        {SUGGESTED_QUESTIONS.map((q, i) => {
          const Icon = q.icon;
          return (
            <button
              key={i}
              onClick={() => onPick(q.text)}
              className={`group flex items-start gap-3 text-left p-3.5 rounded-2xl bg-gradient-to-br ${q.tone} border border-gray-200/60 hover:border-foxAmber/40 hover:shadow-md hover:-translate-y-0.5 transition-all duration-200`}
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <span className="shrink-0 w-8 h-8 rounded-xl bg-white/80 flex items-center justify-center text-foxAmber shadow-sm group-hover:scale-110 transition-transform">
                <Icon className="w-4 h-4" />
              </span>
              <span className="text-sm text-midnightCharcoal leading-snug pt-1">{q.text}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-6 text-[0.7rem] text-gray-400 flex items-center gap-1">
        <MessageCircle className="w-3 h-3" />
        狐狸只基于本课材料回答,问超范围的它会直接拒绝
      </p>
    </div>
  );
}
