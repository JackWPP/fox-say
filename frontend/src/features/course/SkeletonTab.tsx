import { useEffect, useState } from "react";
import { GitBranch, Lightbulb, RefreshCw } from "lucide-react";
import { useSkeleton } from "./useSkeleton";
import SkeletonTree from "./SkeletonTree";
import { foxCopy } from "../../shared/fox-copy";

interface SkeletonTabProps {
  courseId: string;
  onConceptClick?: (concept: string) => void;
}

export default function SkeletonTab({ courseId, onConceptClick }: SkeletonTabProps) {
  const { skeleton, loading, error, notFound, refetch } = useSkeleton(courseId);
  const [showSurprise, setShowSurprise] = useState(false);

  // SSE listener for skeleton_ready event
  useEffect(() => {
    const eventsUrl = `/api/courses/${courseId}/events`;
    const es = new EventSource(eventsUrl);

    es.addEventListener("skeleton_ready", () => {
      setShowSurprise(true);
      refetch();
      setTimeout(() => setShowSurprise(false), 10000);
    });

    es.onerror = () => {
      es.close();
    };

    return () => es.close();
  }, [courseId, refetch]);

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
        <p className="text-red-500 text-sm mb-3">{foxCopy.errors.loadFailed}</p>
        <button
          onClick={refetch}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          {foxCopy.errors.retry}
        </button>
      </div>
    );
  }

  if (notFound || !skeleton) {
    return (
      <div className="text-center py-16 text-gray-400">
        <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p className="text-lg">{foxCopy.skeleton.empty}</p>
        <p className="text-xs mt-2 text-gray-300">{foxCopy.skeleton.processing}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* "First Surprise" notification */}
      {showSurprise && (
        <div className="bg-foxAmber/10 border border-foxAmber/30 rounded-xl p-4 animate-in">
          <p className="text-sm text-midnightCharcoal">
            {foxCopy.skeleton.done.replace("{chapter}", skeleton.difficulty_areas?.[0] || "某个章节")}
          </p>
        </div>
      )}

      {skeleton.core_concepts.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-midnightCharcoal mb-3 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-foxAmber" />
            核心概念 — 点击概念节点进入问答
          </h3>
          <div className="flex flex-wrap gap-1.5 mb-4">
            {skeleton.core_concepts.map((concept, i) => (
              <button
                key={i}
                onClick={() => onConceptClick?.(concept)}
                className="text-xs bg-foxAmber/10 text-foxAmber border border-foxAmber/20 px-2.5 py-1 rounded-full font-medium hover:bg-foxAmber/20 transition-colors cursor-pointer"
              >
                {concept}
              </button>
            ))}
          </div>
        </div>
      )}

      <SkeletonTree skeleton={skeleton} onConceptClick={onConceptClick} />
    </div>
  );
}
