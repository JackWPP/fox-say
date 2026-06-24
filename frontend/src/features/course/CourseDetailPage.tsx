import { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import { ArrowLeft, FileText, GitBranch, MessageCircle, Network, Zap, X, BookOpen, HelpCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCourse } from "../bookshelf/useCourses";
import MaterialsTab from "./MaterialsTab";
import SkeletonTab from "./SkeletonTab";
import ChatTab from "./ChatTab";
import ReviewTab from "./ReviewTab";
import KnowledgeGraphTab from "./KnowledgeGraphTab";
import LectureView from "./LectureView";
import QuizView from "./QuizView";
import { useSkeleton } from "./useSkeleton";
import { API_BASE } from "../../shared/api";

type StudyMode = "exam" | "study";
type Tab = "materials" | "skeleton" | "qa" | "kg" | "review" | "lecture" | "quiz";

const allTabs: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: "materials", label: "材料", icon: FileText },
  { key: "skeleton", label: "骨架", icon: GitBranch },
  { key: "qa", label: "问答", icon: MessageCircle },
  { key: "kg", label: "知识图谱", icon: Network },
  { key: "lecture", label: "讲义", icon: BookOpen },
  { key: "quiz", label: "练习", icon: HelpCircle },
  { key: "review", label: "备考", icon: Zap },
];

const studyTabOrder: Tab[] = ["materials", "skeleton", "qa", "kg", "lecture", "quiz", "review"];
const examTabOrder: Tab[] = ["review", "skeleton", "qa", "kg", "lecture", "quiz", "materials"];

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
  const { skeleton } = useSkeleton(courseId ?? "");
  const chapters = skeleton?.chapters ?? [];

  // 第一个惊喜:监听 course_ready 事件
  const [toast, setToast] = useState<{ message: string; weakAreas: string[]; coreConcepts: string[] } | null>(null);

  useEffect(() => {
    if (!courseId) return;
    const es = new EventSource(`${API_BASE}/courses/${courseId}/events`);
    es.addEventListener("course_ready", (e) => {
      try {
        const data = JSON.parse(e.data);
        setToast({
          message: data.message || "你的课程已准备好了！",
          weakAreas: data.weak_areas || [],
          coreConcepts: data.core_concepts || [],
        });
      } catch { /* ignore */ }
    });
    return () => es.close();
  }, [courseId]);

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
      {/* 第一个惊喜:课程就绪 toast */}
      {toast && (
        <div className="mb-4 bg-foxAmber/10 border border-foxAmber/30 rounded-xl px-5 py-4 shadow-sm fox-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-sm font-semibold text-midnightCharcoal mb-1">🦊 {toast.message}</p>
              {toast.coreConcepts.length > 0 && (
                <p className="text-xs text-gray-600 mb-1">
                  核心概念：{toast.coreConcepts.join("、")}
                </p>
              )}
              {toast.weakAreas.length > 0 && (
                <p className="text-xs text-red-500">
                  薄弱区域：{toast.weakAreas.join("、")}
                </p>
              )}
            </div>
            <button
              onClick={() => setToast(null)}
              className="p-1 rounded-lg hover:bg-gray-100 transition-colors text-gray-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

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
      {activeTab === "lecture" && <LectureView courseId={courseId} chapters={chapters} />}
      {activeTab === "quiz" && <QuizView courseId={courseId} chapters={chapters} />}
      {activeTab === "review" && <ReviewTab courseId={courseId} course={course ?? undefined} />}
    </div>
  );
}
