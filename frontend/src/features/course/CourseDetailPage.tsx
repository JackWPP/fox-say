import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { ArrowLeft, FileText, GitBranch, MessageCircle, Network, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCourse } from "../bookshelf/useCourses";
import MaterialsTab from "./MaterialsTab";
import SkeletonTab from "./SkeletonTab";
import ChatTab from "./ChatTab";
import ReviewTab from "./ReviewTab";
import KnowledgeGraphTab from "./KnowledgeGraphTab";

type StudyMode = "exam" | "study";
type Tab = "materials" | "skeleton" | "qa" | "kg" | "review";

const allTabs: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: "materials", label: "材料", icon: FileText },
  { key: "skeleton", label: "骨架", icon: GitBranch },
  { key: "qa", label: "问答", icon: MessageCircle },
  { key: "kg", label: "知识图谱", icon: Network },
  { key: "review", label: "备考", icon: Zap },
];

const studyTabOrder: Tab[] = ["materials", "skeleton", "qa", "kg", "review"];
const examTabOrder: Tab[] = ["review", "skeleton", "qa", "kg", "materials"];

export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [studyMode, setStudyMode] = useState<StudyMode>(() => {
    const saved = localStorage.getItem("foxsay_mode");
    return saved === "exam" ? "exam" : "study";
  });

  const tabOrder = studyMode === "exam" ? examTabOrder : studyTabOrder;
  const defaultTab = studyMode === "exam" ? "review" : "materials";
  const [activeTab, setActiveTab] = useState<Tab>(defaultTab);
  const [prefillQuestion, setPrefillQuestion] = useState("");

  const { course } = useCourse(courseId ?? "");

  const handleConceptClick = (concept: string) => {
    setPrefillQuestion(`请解释"${concept}"`);
    setActiveTab("qa");
  };

  useEffect(() => {
    localStorage.setItem("foxsay_mode", studyMode);
    if (studyMode === "exam" && activeTab === "materials") {
      setActiveTab("review");
    }
  }, [studyMode]);

  const toggleMode = () => {
    setStudyMode((prev) => (prev === "exam" ? "study" : "exam"));
  };

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
        <div className="flex-1" />
        <button
          onClick={toggleMode}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
            studyMode === "exam"
              ? "bg-red-500/10 text-red-500 border border-red-500/20"
              : "bg-foxAmber/10 text-foxAmber border border-foxAmber/20"
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          {studyMode === "exam" ? "超级备考" : "日常学习"}
        </button>
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-6 overflow-x-auto">
        {tabOrder.map((key) => {
          const tab = allTabs.find((t) => t.key === key)!;
          const Icon = tab.icon;
          return (
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
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === "materials" && <MaterialsTab courseId={courseId} />}
      {activeTab === "skeleton" && <SkeletonTab courseId={courseId} onConceptClick={handleConceptClick} />}
      {activeTab === "qa" && <ChatTab courseId={courseId} prefillQuestion={prefillQuestion} onPrefillConsumed={() => setPrefillQuestion("")} />}
      {activeTab === "kg" && <KnowledgeGraphTab courseId={courseId} />}
      {activeTab === "review" && <ReviewTab courseId={courseId} course={course ?? undefined} />}
    </div>
  );
}
