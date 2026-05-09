import { useState } from "react";
import { ChevronDown, ChevronRight, BookOpen, AlertTriangle } from "lucide-react";
import type { CourseSkeletonChapter, Importance } from "../../shared/types";

const importanceConfig: Record<Importance, { label: string; color: string }> = {
  high: { label: "高", color: "bg-red-100 text-red-700" },
  medium: { label: "中", color: "bg-foxAmber/20 text-foxAmber" },
  low: { label: "低", color: "bg-gray-100 text-gray-600" },
};

interface ChapterCardProps {
  chapter: CourseSkeletonChapter;
}

function ChapterCard({ chapter }: ChapterCardProps) {
  const [expanded, setExpanded] = useState(true);
  const imp = importanceConfig[chapter.importance];

  return (
    <div className="bg-white rounded-lg border border-gray-100 overflow-hidden hover:border-foxAmber/30 transition-colors">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
        )}
        <BookOpen className="w-4 h-4 text-foxAmber shrink-0" />
        <span className="flex-1 text-sm font-medium text-midnightCharcoal">
          {chapter.title}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${imp.color}`}>
          {imp.label}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          <div className="ml-7">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-gray-500">考试权重</span>
              <div className="flex-1 bg-gray-100 rounded-full h-2 max-w-[120px]">
                <div
                  className="bg-foxAmber h-2 rounded-full transition-all"
                  style={{ width: `${Math.min(chapter.exam_weight, 100)}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">{chapter.exam_weight}%</span>
            </div>

            {chapter.key_concepts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {chapter.key_concepts.map((concept, i) => (
                  <span
                    key={i}
                    className="text-xs bg-midnightCharcoal/5 text-midnightCharcoal px-2 py-1 rounded-md"
                  >
                    {concept}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface SkeletonTreeProps {
  chapters: CourseSkeletonChapter[];
  difficultyAreas: string[];
  prerequisiteChain: Array<[string, string]>;
}

export default function SkeletonTree({
  chapters,
  difficultyAreas,
  prerequisiteChain,
}: SkeletonTreeProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-midnightCharcoal mb-3 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-foxAmber" />
          章节结构
        </h3>
        <div className="space-y-2">
          {chapters.map((ch) => (
            <ChapterCard key={ch.id} chapter={ch} />
          ))}
        </div>
      </div>

      {difficultyAreas.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-midnightCharcoal mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-foxAmber" />
            难点区域
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {difficultyAreas.map((area, i) => (
              <span
                key={i}
                className="text-xs bg-foxAmber/15 text-foxAmber px-2.5 py-1 rounded-full font-medium"
              >
                {area}
              </span>
            ))}
          </div>
        </div>
      )}

      {prerequisiteChain.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-midnightCharcoal mb-3 flex items-center gap-2">
            <span className="text-foxAmber">→</span>
            先修链路
          </h3>
          <div className="space-y-1.5">
            {prerequisiteChain.map(([from, to], i) => (
              <div
                key={i}
                className="flex items-center gap-2 text-sm text-gray-600"
              >
                <span className="bg-midnightCharcoal/5 px-2 py-0.5 rounded text-xs">
                  {from}
                </span>
                <span className="text-foxAmber font-medium">→</span>
                <span className="bg-midnightCharcoal/5 px-2 py-0.5 rounded text-xs">
                  {to}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
