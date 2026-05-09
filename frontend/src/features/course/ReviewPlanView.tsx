import { Clock, Flame, AlertTriangle } from "lucide-react";
import type { ReviewPlan, Importance } from "../../shared/types";

const priorityConfig: Record<Importance, { label: string; color: string }> = {
  high: { label: "高优先", color: "bg-red-100 text-red-700 border-red-200" },
  medium: { label: "中优先", color: "bg-foxAmber/20 text-foxAmber border-foxAmber/30" },
  low: { label: "低优先", color: "bg-gray-100 text-gray-500 border-gray-200" },
};

interface ReviewPlanViewProps {
  plan: ReviewPlan;
}

export default function ReviewPlanView({ plan }: ReviewPlanViewProps) {
  return (
    <div className="space-y-6">
      <div className="relative">
        <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-foxAmber/20" />

        <div className="space-y-3">
          {plan.daily_plan.map((day) => {
            const pri = priorityConfig[day.priority];
            return (
              <div key={day.day_index} className="relative flex items-start gap-4 pl-1">
                <div className="relative z-10 w-8 h-8 rounded-full bg-foxAmber text-midnightCharcoal flex items-center justify-center text-xs font-bold shrink-0 shadow-sm">
                  {day.day_index}
                </div>

                <div className="flex-1 bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-midnightCharcoal">
                      Day {day.day_index}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${pri.color}`}>
                      {pri.label}
                    </span>
                  </div>

                  <p className="mt-1.5 text-sm text-gray-700">{day.focus}</p>

                  <div className="mt-2 flex items-center gap-1.5 text-xs text-gray-400">
                    <Clock className="w-3 h-3" />
                    <span>{day.suggested_minutes} 分钟</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {(plan.likely_exam_points.length > 0 || plan.weak_areas.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {plan.likely_exam_points.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
              <div className="flex items-center gap-1.5 text-sm font-semibold text-midnightCharcoal mb-2">
                <Flame className="w-4 h-4 text-red-500" />
                <span>可能考点</span>
              </div>
              <ul className="space-y-1.5">
                {plan.likely_exam_points.map((point, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-sm text-gray-600">
                    <span className="text-red-400 mt-0.5">🔥</span>
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {plan.weak_areas.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-100 px-4 py-3 shadow-sm">
              <div className="flex items-center gap-1.5 text-sm font-semibold text-midnightCharcoal mb-2">
                <AlertTriangle className="w-4 h-4 text-foxAmber" />
                <span>薄弱区域</span>
              </div>
              <ul className="space-y-1.5">
                {plan.weak_areas.map((area, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-sm text-gray-600">
                    <span className="text-foxAmber mt-0.5">⚠️</span>
                    <span>{area}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
