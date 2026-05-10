import { FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage as ChatMessageType } from "./useChat";
import ToolCallIndicator from "./ToolCallIndicator";

function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p className="whitespace-pre-wrap mb-1 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-bold text-warmWhite">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        code: ({ children, className }) => {
          const isInline = !className;
          return isInline
            ? <code className="bg-white/10 px-1 py-0.5 rounded text-xs">{children}</code>
            : <code className="block bg-white/10 px-3 py-2 rounded-lg text-xs overflow-x-auto my-2">{children}</code>;
        },
        pre: ({ children }) => <pre className="my-2">{children}</pre>,
        ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>,
        li: ({ children }) => <li className="text-sm">{children}</li>,
        a: ({ href, children }) => (
          <a href={href} className="text-foxAmber underline hover:text-foxAmber/80" target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-foxAmber/30 pl-3 my-2 italic opacity-80">{children}</blockquote>
        ),
        h3: ({ children }) => <h3 className="text-base font-semibold mt-3 mb-1">{children}</h3>,
        h4: ({ children }) => <h4 className="text-sm font-semibold mt-2 mb-1">{children}</h4>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === "user";
  const isRefusal = message.role === "assistant" && message.confidenceStatus === "out_of_scope";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-foxAmber text-midnightCharcoal rounded-2xl rounded-br-sm px-4 py-3 text-sm">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm ${
          isRefusal
            ? "bg-gray-100 text-gray-400"
            : "bg-midnightCharcoal text-warmWhite"
        }`}
      >
        {isRefusal && (
          <span className="inline-block mr-1.5">🦊</span>
        )}
        {isRefusal ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <MarkdownRenderer content={message.content} />
        )}

        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallIndicator toolCalls={message.toolCalls} />
        )}

        {message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/10 space-y-1.5">
            {message.citations.map((c, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 text-xs opacity-80"
              >
                <FileText className="w-3 h-3 shrink-0" />
                <span>来自 {c.file_name} · {c.locator}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
