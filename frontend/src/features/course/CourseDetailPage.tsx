import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, Zap, X, MessageCircle, BookMarked } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCourse } from "../bookshelf/useCourses";
import MaterialsTab from "./MaterialsTab";
import SkeletonTab from "./SkeletonTab";
import KnowledgeGraphTab from "./KnowledgeGraphTab";
import LectureView from "./LectureView";
import QuizView from "./QuizView";
import ReviewTab from "./ReviewTab";
import { useSkeleton } from "./useSkeleton";
import { useMaterials } from "./useMaterials";
import { useKnowledgeStatus } from "./useKnowledgeStatus";
import { API_BASE } from "../../shared/api";
import SourcesPanel from "./SourcesPanel";
import ChatWorkspace from "./ChatWorkspace";
import StudioPanel from "./StudioPanel";

type StudyMode = "exam" | "study";
type ActiveView = "chat" | "skeleton" | "kg" | "lecture" | "quiz" | "review" | "materials";

function formatCountdown(examDate?: string): { text: string; days: number } | null {
  if (!examDate) return null;
  const exam = new Date(examDate);
  const now = new Date();
  const diffMs = exam.getTime() - now.getTime();
  if (diffMs < 0) return { text: "已过期", days: -1 };
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  return { text: `距考试还有 ${diffDays} 天`, days: diffDays };
}

export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const [studyMode, setStudyMode] = useState<StudyMode>(() => {
    const saved = localStorage.getItem("foxsay_mode");
    return saved === "exam" ? "exam" : "study";
  });

  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const [prefillQuestion, setPrefillQuestion] = useState("");
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth < 1280;
    }
    return false;
  });

  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [selectedNoteIds, setSelectedNoteIds] = useState<string[]>([]);

  const { course } = useCourse(courseId ?? "");
  const { skeleton } = useSkeleton(courseId ?? "");
  const { materials, refetch: refetchMaterials } = useMaterials(courseId ?? "");
  const {
    knowledgeStatus,
    loading: knowledgeStatusLoading,
    error: knowledgeStatusError,
    autoRefreshPaused: knowledgeStatusAutoRefreshPaused,
    refresh: refreshKnowledgeStatus,
  } = useKnowledgeStatus(courseId ?? "");
  const chapters = skeleton?.chapters ?? [];

  useEffect(() => {
    setSelectedSourceIds(materials.map(m => m.id).filter(id => !selectedSourceIds.includes(id) || materials.some(m => m.id === id)));
    const readyMaterialIds = materials.filter(m => m.status === "ready").map(m => m.id);
    if (selectedSourceIds.length === 0 && readyMaterialIds.length > 0) {
      setSelectedSourceIds(readyMaterialIds);
    }
  }, [materials]);

  const [toast, setToast] = useState<{ message: string; weakAreas: string[]; coreConcepts: string[] } | null>(null);
  const [termToast, setTermToast] = useState<{ termCount: number } | null>(null);

  useEffect(() => {
    if (!courseId) return;
    const es = new EventSource(`${API_BASE}/courses/${courseId}/events`);
    es.addEventListener("course_ready", (e) => {
      // SSE is only a refresh hint. The durable KnowledgeStatus API remains
      // the source of truth for material evidence and projection state.
      void refreshKnowledgeStatus();
      try {
        const data = JSON.parse(e.data);
        setToast({
          message: data.message || "你的课程已准备好了！",
          weakAreas: data.weak_areas || [],
          coreConcepts: data.core_concepts || [],
        });
        refetchMaterials();
      } catch { /* ignore */ }
    });
    es.addEventListener("terminology_ready", (e) => {
      try {
        const data = JSON.parse(e.data);
        setTermToast({ termCount: data.term_count || 0 });
        setTimeout(() => setTermToast(null), 5000);
      } catch { /* ignore */ }
    });
    return () => es.close();
  }, [courseId, refetchMaterials, refreshKnowledgeStatus]);

  const handleConceptClick = (concept: string) => {
    setPrefillQuestion(`请解释"${concept}"`);
    setActiveView("chat");
  };

  useEffect(() => {
    localStorage.setItem("foxsay_mode", studyMode);
  }, [studyMode]);

  useEffect(() => {
    if (activeView === "review" && studyMode !== "exam") {
      setStudyMode("exam");
    }
  }, [activeView, studyMode]);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1280) {
        setRightCollapsed(true);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleSelectionChange = (sourceIds: string[], noteIds: string[]) => {
    setSelectedSourceIds(sourceIds);
    setSelectedNoteIds(noteIds);
  };

  if (!courseId) return null;

  const countdown = formatCountdown(course?.exam_date);
  const isExamMode = studyMode === "exam";

  const renderActiveView = () => {
    switch (activeView) {
      case "chat":
        return (
          <ChatWorkspace
            courseId={courseId}
            courseTitle={course?.title || "课程"}
            course={course ?? undefined}
            sourceCount={materials.length}
            selectedSourceIds={selectedSourceIds}
            selectedNoteIds={selectedNoteIds}
            prefillQuestion={prefillQuestion}
            onPrefillConsumed={() => setPrefillQuestion("")}
            onSwitchToMaterials={() => setActiveView("materials")}
          />
        );
      case "skeleton":
        return <SkeletonTab courseId={courseId} onConceptClick={handleConceptClick} />;
      case "kg":
        return (
          <KnowledgeGraphTab
            courseId={courseId}
            onAskAboutConcept={handleConceptClick}
          />
        );
      case "lecture":
        return <LectureView courseId={courseId} chapters={chapters} />;
      case "quiz":
        return <QuizView courseId={courseId} chapters={chapters} />;
      case "review":
        return <ReviewTab courseId={courseId} course={course ?? undefined} />;
      case "materials":
        return <MaterialsTab courseId={courseId} onKnowledgeChanged={refreshKnowledgeStatus} />;
      default:
        return null;
    }
  };

  return (
    <div className="h-[calc(100vh-56px)] flex flex-col bg-slate-50 overflow-hidden">
      {termToast && (
        <div className="mx-4 mt-3 bg-violet-50 border border-violet-200 rounded-xl px-4 py-2.5 shadow-sm fox-fade-in shrink-0 z-20 flex items-center gap-2">
          <BookMarked className="w-4 h-4 text-violet-500 shrink-0" />
          <p className="text-xs text-violet-700 flex-1">
            词典构建完成，提取到 <span className="font-semibold">{termToast.termCount}</span> 条专有名词，问问题时将自动召回
          </p>
          <button onClick={() => setTermToast(null)} className="p-1 rounded hover:bg-violet-100 text-violet-400">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {toast && (
        <div className="mx-4 mt-3 bg-foxAmber/10 border border-foxAmber/30 rounded-xl px-5 py-4 shadow-sm fox-fade-in shrink-0 z-20">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-sm font-semibold text-midnightCharcoal mb-1">🦊 {toast.message}</p>
              {toast.coreConcepts.length > 0 && (
                <p className="text-xs text-slate-600 mb-1">
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
              className="p-1 rounded-lg hover:bg-slate-100 transition-colors text-slate-400"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="h-14 px-4 flex items-center gap-3 border-b border-slate-200 bg-white shrink-0">
        <button
          onClick={() => navigate("/")}
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-slate-500 hover:text-midnightCharcoal"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-lg font-bold text-midnightCharcoal truncate">
          {course?.title || "课程详情"}
        </h1>

        <div className="flex-1" />

        {countdown && (
          <div className={`px-3 py-1 rounded-lg text-sm font-medium ${
            isExamMode
              ? "bg-foxAmber/15 text-foxAmber"
              : countdown.days >= 0 && countdown.days <= 7
              ? "bg-red-50 text-red-500"
              : "bg-slate-100 text-slate-600"
          }`}>
            {countdown.text}
          </div>
        )}

        <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-0.5">
          <button
            onClick={() => setStudyMode("study")}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              studyMode === "study"
                ? "bg-white text-midnightCharcoal shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            日常学习
          </button>
          <button
            onClick={() => {
              if (studyMode !== "exam") {
                setStudyMode("exam");
                if (activeView === "chat") {
                  setActiveView("review");
                }
              } else {
                setStudyMode("study");
              }
            }}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              studyMode === "exam"
                ? "bg-foxAmber text-midnightCharcoal shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            超级备考
          </button>
        </div>

        <div className="flex items-center gap-1 ml-1">
          <button
            onClick={() => setLeftCollapsed(!leftCollapsed)}
            className={`p-2 rounded-lg transition-colors ${
              leftCollapsed
                ? "bg-foxAmber/10 text-foxAmber"
                : "hover:bg-slate-100 text-slate-500 hover:text-midnightCharcoal"
            }`}
            title={leftCollapsed ? "展开来源面板" : "折叠来源面板"}
          >
            {leftCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setRightCollapsed(!rightCollapsed)}
            className={`p-2 rounded-lg transition-colors ${
              rightCollapsed
                ? "hover:bg-slate-100 text-slate-500 hover:text-midnightCharcoal"
                : "bg-slate-100 text-midnightCharcoal"
            }`}
            title={rightCollapsed ? "展开 Studio 面板" : "折叠 Studio 面板"}
          >
            {rightCollapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div
          className={`bg-slate-50 border-r border-slate-200 flex flex-col transition-all duration-200 ease-out overflow-hidden ${
            leftCollapsed ? "w-12" : "w-64"
          }`}
        >
          <SourcesPanel
            courseId={courseId}
            collapsed={leftCollapsed}
            selectedSourceIds={selectedSourceIds}
            selectedNoteIds={selectedNoteIds}
            onSelectionChange={handleSelectionChange}
            knowledgeStatus={knowledgeStatus}
            knowledgeStatusLoading={knowledgeStatusLoading}
            knowledgeStatusError={knowledgeStatusError}
            knowledgeStatusAutoRefreshPaused={knowledgeStatusAutoRefreshPaused}
            onRefreshKnowledgeStatus={refreshKnowledgeStatus}
          />
        </div>

        <div className="flex-1 flex flex-col bg-slate-50 overflow-hidden">
          {activeView !== "chat" && (
            <div className="h-10 px-4 flex items-center gap-2 border-b border-slate-100 bg-white shrink-0">
              <button
                onClick={() => setActiveView("chat")}
                className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-foxAmber transition-colors"
              >
                <MessageCircle className="w-4 h-4" />
                返回聊天
              </button>
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            {renderActiveView()}
          </div>
        </div>

        <div
          className={`bg-white border-l border-slate-200 flex flex-col transition-all duration-200 ease-out overflow-hidden ${
            rightCollapsed ? "w-0" : "w-72"
          }`}
        >
          {!rightCollapsed && (
            <StudioPanel
              courseId={courseId}
              activeView={activeView}
              onViewChange={setActiveView}
              selectedNoteIds={selectedNoteIds}
              onNoteSelectionChange={(ids) => setSelectedNoteIds(ids)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
