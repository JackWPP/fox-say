import { GitBranch, Lightbulb, RefreshCw } from "lucide-react";
import { useSkeleton } from "./useSkeleton";
import SkeletonTree from "./SkeletonTree";

interface SkeletonTabProps {
  courseId: string;
}

export default function SkeletonTab({ courseId }: SkeletonTabProps) {
  const { skeleton, loading, error, notFound, refetch } = useSkeleton(courseId);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 text-sm mb-3">加载失败: {error}</p>
        <button
          onClick={refetch}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          重试
        </button>
      </div>
    );
  }

  if (notFound || !skeleton) {
    return (
      <div className="text-center py-16 text-gray-400">
        <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p className="text-lg">材料还在消化中，骨架图即将生成 🦊</p>
        <p className="text-xs mt-2 text-gray-300">狐狸正在啃材料，每 10 秒自动检查...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {skeleton.core_concepts.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-midnightCharcoal mb-3 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-foxAmber" />
            核心概念
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {skeleton.core_concepts.map((concept, i) => (
              <span
                key={i}
                className="text-xs bg-foxAmber/10 text-foxAmber border border-foxAmber/20 px-2.5 py-1 rounded-full font-medium"
              >
                {concept}
              </span>
            ))}
          </div>
        </div>
      )}

      <SkeletonTree
        chapters={skeleton.chapters}
        difficultyAreas={skeleton.difficulty_areas}
        prerequisiteChain={skeleton.prerequisite_chain}
      />
    </div>
  );
}
