import { useRef, useEffect } from "react";
import { MessageCircle } from "lucide-react";
import { useChat } from "./useChat";
import ChatMessage from "./ChatMessage";
import ChatInput from "./ChatInput";

interface ChatTabProps {
  courseId: string;
}

export default function ChatTab({ courseId }: ChatTabProps) {
  const { messages, sendQuestion, loading } = useChat(courseId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)]">
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <MessageCircle className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-lg">有什么关于课程的问题？尽管问 🦊</p>
            <p className="text-xs mt-2 text-gray-300">狐狸只基于课程材料回答，不会瞎编哦</p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            {loading && (
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
        <ChatInput onSend={sendQuestion} loading={loading} />
      </div>
    </div>
  );
}
