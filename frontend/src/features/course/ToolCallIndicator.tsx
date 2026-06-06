import { Search, BookOpen, Zap, Loader2 } from "lucide-react";
import type { ToolCallState } from "../../shared/types";

const toolLabels: Record<string, { label: string; icon: typeof Search }> = {
  search_course_materials: { label: "搜索课程材料", icon: Search },
  get_course_structure: { label: "获取课程结构", icon: BookOpen },
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
