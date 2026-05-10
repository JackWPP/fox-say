import { useRef, useEffect, useState } from "react";
import { MessageCircle, Plus, Trash2 } from "lucide-react";
import { useChat, type ChatSession } from "./useChat";
import { foxCopy } from "../../shared/fox-copy";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";
import ToolCallIndicator from "./ToolCallIndicator";

interface ChatTabProps {
  courseId: string;
  prefillQuestion?: string;
  onPrefillConsumed?: () => void;
}

export default function ChatTab({ courseId, prefillQuestion, onPrefillConsumed }: ChatTabProps) {
  const {
    messages, sendQuestion, loading, streamingBuffer, activeToolCalls,
    sessions, activeSessionId, switchSession, createSession, deleteSession,
  } = useChat(courseId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [showSessionList, setShowSessionList] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingBuffer]);

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)]">
      {/* Session bar */}
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-gray-100">
        <button
          onClick={() => setShowSessionList(!showSessionList)}
          className="flex-1 text-left text-sm font-medium text-midnightCharcoal truncate hover:text-foxAmber transition-colors"
        >
          {activeSession?.title || "New Chat"}
        </button>
        <button
          onClick={async () => { await createSession("New Chat"); }}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-foxAmber transition-colors"
          title="New session"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          onClick={() => { if (activeSessionId) deleteSession(activeSessionId); }}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-red-500 transition-colors"
          title="Delete session"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Session list dropdown */}
      {showSessionList && (
        <div className="mb-3 bg-white border border-gray-200 rounded-lg shadow-sm max-h-40 overflow-y-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => { switchSession(s.id); setShowSessionList(false); }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                s.id === activeSessionId
                  ? "bg-foxAmber/10 text-foxAmber font-medium"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <div className="truncate">{s.title}</div>
              <div className="text-xs text-gray-400">{s.updated_at?.slice(0, 10)}</div>
            </button>
          ))}
          {sessions.length === 0 && (
            <div className="px-3 py-4 text-center text-sm text-gray-400">No sessions yet</div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <MessageCircle className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-lg">{foxCopy.chat.empty}</p>
            <p className="text-xs mt-2 text-gray-300">{foxCopy.chat.emptyHint}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            {activeToolCalls.length > 0 && (
              <div className="flex justify-start mb-2">
                <ToolCallIndicator toolCalls={activeToolCalls} />
              </div>
            )}
            {streamingBuffer && (
              <div className="flex justify-start mb-2">
                <div className="bg-midnightCharcoal text-warmWhite rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
                  <p className="whitespace-pre-wrap">{streamingBuffer}</p>
                </div>
              </div>
            )}
            {loading && !streamingBuffer && activeToolCalls.length === 0 && (
              <div className="flex justify-start">
                <div className="bg-midnightCharcoal text-warmWhite rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
                  <div className="flex items-center gap-2">
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
