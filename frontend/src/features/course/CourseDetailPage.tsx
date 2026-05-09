import { useState } from "react";
import { useParams } from "react-router-dom";
import { ArrowLeft, FileText, GitBranch, MessageCircle, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCourse } from "../bookshelf/useCourses";
import MaterialsTab from "./MaterialsTab";
import SkeletonTab from "./SkeletonTab";
import ChatTab from "./ChatTab";
import ReviewTab from "./ReviewTab";

type Tab = "materials" | "skeleton" | "qa" | "review";

const tabs: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: "materials", label: "材料", icon: FileText },
  { key: "skeleton", label: "骨架", icon: GitBranch },
  { key: "qa", label: "问答", icon: MessageCircle },
  { key: "review", label: "备考", icon: Zap },
];

export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>("materials");
  const { course } = useCourse(courseId ?? "");

  if (!courseId) return null;

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate("/")}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-500 hover:text-midnightCharcoal"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-xl font-bold text-midnightCharcoal">课程详情</h1>
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-6 overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === key
                ? "border-foxAmber text-foxAmber"
                : "border-transparent text-gray-500 hover:text-midnightCharcoal"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {activeTab === "materials" && <MaterialsTab courseId={courseId} />}
      {activeTab === "skeleton" && <SkeletonTab courseId={courseId} />}
      {activeTab === "qa" && <ChatTab courseId={courseId} />}
      {activeTab === "review" && <ReviewTab courseId={courseId} course={course ?? undefined} />}
    </div>
  );
}
