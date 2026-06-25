import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import oneLight from "react-syntax-highlighter/dist/esm/styles/prism/one-light";
import js from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import ts from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import py from "react-syntax-highlighter/dist/esm/languages/prism/python";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import markdown from "react-syntax-highlighter/dist/esm/languages/prism/markdown";
import { Check, Copy } from "lucide-react";

// Register only the languages we care about — keeps the bundle small.
SyntaxHighlighter.registerLanguage("javascript", js);
SyntaxHighlighter.registerLanguage("js", js);
SyntaxHighlighter.registerLanguage("typescript", ts);
SyntaxHighlighter.registerLanguage("ts", ts);
SyntaxHighlighter.registerLanguage("python", py);
SyntaxHighlighter.registerLanguage("py", py);
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("sh", bash);
SyntaxHighlighter.registerLanguage("shell", bash);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("jsx", jsx);
SyntaxHighlighter.registerLanguage("tsx", tsx);
SyntaxHighlighter.registerLanguage("markdown", markdown);
SyntaxHighlighter.registerLanguage("md", markdown);

interface CodeBlockProps {
  className?: string;
  children?: ReactNode;
  inline?: boolean;
  light?: boolean;
}

function extractText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return extractText((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

function CodeBlock({ className, children, light }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const raw = extractText(children);
  // react-markdown passes the language as `language-xyz`
  const language = (className || "").replace(/^language-/, "").trim() || "text";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(raw.replace(/\n$/, ""));
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      // Fallback for older browsers / iframe contexts
      const ta = document.createElement("textarea");
      ta.value = raw.replace(/\n$/, "");
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch { /* ignore */ }
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  };

  const wrapperClass = light ? "fox-code-block fox-code-block-light" : "fox-code-block";
  const codeStyle = light ? (oneLight as Record<string, React.CSSProperties>) : (oneDark as Record<string, React.CSSProperties>);
  const lineNumStyle = light
    ? { color: "rgba(100,116,139,0.4)", fontSize: "0.7rem", minWidth: "1.8em" }
    : { color: "rgba(255,247,237,0.25)", fontSize: "0.7rem", minWidth: "1.8em" };

  return (
    <div className={wrapperClass}>
      <div className="fox-code-header">
        <span className="font-mono">{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          className={`fox-code-copy ${copied ? "copied" : ""}`}
          aria-label="复制代码"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3" />
              <span>已复制</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>复制</span>
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={codeStyle}
        customStyle={{ margin: 0, background: "transparent" }}
        codeTagProps={{ style: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" } }}
        wrapLongLines={false}
        showLineNumbers={raw.split("\n").length > 4}
        lineNumberStyle={lineNumStyle}
      >
        {raw.replace(/\n$/, "")}
      </SyntaxHighlighter>
    </div>
  );
}

const components: Components = {
  p: ({ children }) => <p>{children}</p>,
  strong: ({ children }) => <strong>{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  ul: ({ children }) => <ul>{children}</ul>,
  ol: ({ children }) => <ol>{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  blockquote: ({ children }) => <blockquote>{children}</blockquote>,
  h1: ({ children }) => <h1>{children}</h1>,
  h2: ({ children }) => <h2>{children}</h2>,
  h3: ({ children }) => <h3>{children}</h3>,
  h4: ({ children }) => <h4>{children}</h4>,
  hr: () => <hr />,
  table: ({ children }) => <table>{children}</table>,
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => <th>{children}</th>,
  td: ({ children }) => <td>{children}</td>,
  code: ({ className, children }) => {
    // react-markdown gives a `code` element WITHOUT className for inline code,
    // and WITH className="language-xxx" when nested inside a fenced <pre> block.
    if (className) {
      return <CodeBlock className={className}>{children}</CodeBlock>;
    }
    return <code>{children}</code>;
  },
  pre: ({ children }) => <>{children}</>,
};

interface MarkdownRendererProps {
  content: string;
  /** When true, appends a blinking cursor at the end (for streaming output) */
  streaming?: boolean;
  /** Visual variant: 'default' (dark bg), 'light' (warm light bg), 'ai' (white bg prose) */
  variant?: "default" | "light" | "ai";
  /** @deprecated Use variant="light" instead */
  light?: boolean;
  /** @deprecated Use variant="ai" instead */
  ai?: boolean;
}

// Defense in depth: strip any residual DSML tool-call markup the backend
// may have missed (e.g. from older agent versions or partial streams).
// Mirrors the regex used in `backend/app/services/agent.py`.
// LLM sometimes emits full-width pipes (｜) and/or omits spaces, so the pipe
// class accepts both ASCII '|' (U+007C) and full-width '｜' (U+FF5C).
const PIPE = "[|｜]+";
const DSML_BLOCK_RE = new RegExp(
  `<\\s*${PIPE}\\s*DSML\\s*${PIPE}[^>]*>.*?<\\s*/\\s*${PIPE}\\s*DSML\\s*${PIPE}[^>]*>`,
  "gs",
);
const DSML_TAG_RE = new RegExp(`<\\s*\\/?\\s*${PIPE}\\s*DSML\\s*${PIPE}[^>]*>`, "g");

function stripDSML(text: string): string {
  if (!text) return text;
  if (!text.includes("DSML")) return text;
  return text.replace(DSML_BLOCK_RE, "").replace(DSML_TAG_RE, "").trim();
}

export default function MarkdownRenderer({ content, streaming, variant, light, ai }: MarkdownRendererProps) {
  const safeContent = stripDSML(content);
  const resolvedVariant: "default" | "light" | "ai" = variant || (ai ? "ai" : light ? "light" : "default");
  const className = resolvedVariant === "ai" ? "fox-prose-ai" : resolvedVariant === "light" ? "fox-prose-light" : "fox-prose";
  const codeLight = resolvedVariant === "ai" || resolvedVariant === "light";

  const componentsWithLight: Components = {
    ...components,
    code: ({ className: codeCls, children }: { className?: string; children?: ReactNode }) => {
      if (codeCls) {
        return <CodeBlock className={codeCls} light={codeLight}>{children}</CodeBlock>;
      }
      return <code>{children}</code>;
    },
  };

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={componentsWithLight}>
        {safeContent}
      </ReactMarkdown>
      {streaming && <span className="fox-typing-cursor" aria-hidden="true" />}
    </div>
  );
}
