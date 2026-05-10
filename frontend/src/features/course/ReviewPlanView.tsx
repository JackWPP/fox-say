import { Clock, Flame, AlertTriangle } from "lucide-react";
import type { ReviewPlan, Importance } from "../../shared/types";
import { foxCopy } from "../../shared/fox-copy";

const priorityConfig: Record<Importance, { label: string; color: string }> = {
  high: { label: "高优先", color: "bg-red-100 text-red-700 border-red-200" },
  medium: { label: "中优先", color: "bg-foxAmber/20 text-foxAmber border-foxAmber/30" },
  low: { label: "低优先", color: "bg-gray-100 text-gray-500 border-gray-200" },
};

interface ReviewPlanViewProps {
  plan: ReviewPlan;
  currentDay?: number;
  showFull?: boolean;
}

export default function ReviewPlanView({ plan, currentDay = 1, showFull = false }: ReviewPlanViewProps) {
  const day = plan.daily_plan.find(d => d.day_index === currentDay) || plan.daily_plan[0];
  const pri = priorityConfig[day?.priority || "medium"];

  return (
    <div className="space-y-6">
      {/* Current day focus */}
      <div className="bg-white rounded-xl border-2 border-foxAmber/30 px-5 py-4 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-midnightCharcoal">
            Day {currentDay} / {plan.daily_plan.length}
          </h3>
          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${pri.color}`}>
            {pri.label}
          </span>
        </div>
        <p className="text-sm text-gray-700 leading-relaxed">{day?.focus}</p>
        <div className="mt-3 flex items-center gap-2 text-sm text-gray-500">
          <Clock className="w-4 h-4 text-foxAmber" />
          <span>建议 {day?.suggested_minutes} 分钟</span>
        </div>
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-xs text-gray-500">
            {foxCopy.review.stepStart.replace("{chapter}", `Day ${currentDay}`).replace("{minutes}", String(day?.suggested_minutes || 30))}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="bg-gray-100 rounded-full h-1.5">
        <div
          className="bg-foxAmber h-1.5 rounded-full transition-all"
          style={{ width: `${Math.min((currentDay / plan.daily_plan.length) * 100, 100)}%` }}
        />
      </div>

      {/* Full plan overview (collapsible) */}
      {showFull && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-midnightCharcoal">全部计划</h3>
          <div className="relative">
            <div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-foxAmber/20" />
            <div className="space-y-2">
              {plan.daily_plan.map((d) => {
                const dp = priorityConfig[d.priority];
                return (
                  <div key={d.day_index} className="relative flex items-start gap-3 pl-1">
                    <div className={`relative z-10 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 shadow-sm ${
                      d.day_index === currentDay ? "bg-foxAmber text-midnightCharcoal" :
                      d.day_index < currentDay ? "bg-green-500 text-white" : "bg-gray-200 text-gray-500"
                    }`}>
                      {d.day_index <= currentDay ? "✓" : d.day_index}
                    </div>
                    <div className="flex-1 bg-white rounded-lg border border-gray-100 px-3 py-2">
                      <p className="text-xs text-gray-700">{d.focus.slice(0, 80)}{d.focus.length > 80 ? "..." : ""}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Likely exam points and weak areas */}
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
                  <li key={i} className="text-sm text-gray-600">• {point}</li>
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
                  <li key={i} className="text-sm text-gray-600">• {area}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
