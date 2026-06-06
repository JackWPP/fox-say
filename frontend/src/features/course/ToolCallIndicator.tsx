import { Search, BookOpen, Zap, Loader2, Map, FileQuestion, ListTree, ArrowLeft, FileCode } from "lucide-react";
import type { ToolCallState } from "../../shared/types";

const toolLabels: Record<string, { label: string; icon: typeof Search }> = {
  search_wiki: { label: "搜索 Wiki", icon: Search },
  get_course_map: { label: "获取课程索引", icon: Map },
  get_concept: { label: "获取知识点", icon: FileQuestion },
  get_chapter_outline: { label: "获取章节摘要", icon: ListTree },
  follow_prerequisite: { label: "追溯先修链", icon: ArrowLeft },
  get_source_content: { label: "获取原始材料", icon: FileCode },
  get_review_plan: { label: "获取复习计划", icon: Zap },
};

interface ToolCallIndicatorProps {
  toolCalls: ToolCallState[];
}

export default function ToolCallIndicator({ toolCalls }: ToolCallIndicatorProps) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 my-2">
      {toolCalls.map((tc) => {
        const info = toolLabels[tc.tool] || { label: tc.tool, icon: Search };
        const Icon = info.icon;
        return (
          <span
            key={tc.id}
            className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
              tc.status === "running"
                ? "bg-foxAmber/10 text-foxAmber border border-foxAmber/20"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {tc.status === "running" ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Icon className="w-3 h-3" />
            )}
            {info.label}
          </span>
        );
      })}
    </div>
  );
}
