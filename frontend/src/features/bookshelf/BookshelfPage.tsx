import { useState } from "react";
import { Plus, Table2, RefreshCw } from "lucide-react";
import CourseCard from "./CourseCard";
import CreateCourseModal from "./CreateCourseModal";
import ImportTimetableModal from "./ImportTimetableModal";
import { useCourses } from "./useCourses";
import { foxCopy } from "../../shared/fox-copy";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";

export default function BookshelfPage() {
  const { courses, loading, error, refetch } = useCourses();
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  return (
    <div className="min-h-full bg-slate-50">
      {/* Gradient header banner */}
      <div className="relative overflow-hidden bg-gradient-to-br from-amber-400 via-orange-400 to-amber-500 px-6 md:px-10 pt-8 pb-12">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(255,255,255,0.18),_transparent_60%)]" />
        <div className="absolute bottom-0 left-0 right-0 h-8 bg-slate-50 rounded-t-[2rem]" />
        <div className="relative max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-3xl select-none">🦊</span>
              <h1 className="text-2xl font-bold text-white tracking-tight drop-shadow-sm">
                我的课程
              </h1>
            </div>
            <p className="text-amber-100/90 text-sm pl-[3.25rem]">
              {courses.length > 0
                ? `共 ${courses.length} 门课，今天学什么？`
                : "开始建你的第一门课吧"}
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setImportOpen(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white/20 hover:bg-white/30 text-white text-sm font-medium transition-colors backdrop-blur-sm border border-white/20"
            >
              <Table2 className="w-4 h-4" />
              导入课程表
            </button>
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white hover:bg-amber-50 text-amber-600 text-sm font-bold transition-colors shadow-soft"
            >
              <Plus className="w-4 h-4" />
              创建课程
            </button>
          </div>
        </div>
      </div>

      {/* Content area */}
      <div className="max-w-7xl mx-auto px-6 md:px-10 pb-10 -mt-2">
        {loading && (
          <div className="flex items-center justify-center py-24">
            <Spinner size="lg" />
          </div>
        )}

        {error && (
          <div className="text-center py-24">
            <div className="text-5xl mb-4">😿</div>
            <p className="text-red-500 mb-4 font-medium">加载失败: {error}</p>
            <Button variant="secondary" onClick={refetch}>
              <RefreshCw className="w-4 h-4" />
              重试
            </Button>
          </div>
        )}

        {!loading && !error && courses.length === 0 && (
          <div className="text-center py-20">
            <div className="text-7xl mb-5 select-none fox-float inline-block">🦊</div>
            <p className="text-xl font-bold text-midnightCharcoal mb-2">
              {foxCopy.bookshelf.empty}
            </p>
            <p className="text-slate-500 mb-8 max-w-sm mx-auto text-sm leading-relaxed">
              {foxCopy.bookshelf.emptyHint}
            </p>
            <div className="flex items-center justify-center gap-3">
              <Button
                variant="secondary"
                onClick={() => setImportOpen(true)}
                size="lg"
                className="rounded-xl"
              >
                <Table2 className="w-4 h-4" />
                导入课程表
              </Button>
              <Button
                variant="primary"
                onClick={() => setCreateOpen(true)}
                size="lg"
                className="rounded-xl"
              >
                <Plus className="w-4 h-4" />
                创建课程
              </Button>
            </div>
          </div>
        )}

        {!loading && !error && courses.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6 pt-4">
            {courses.map((course, idx) => (
              <div
                key={course.id}
                className="fox-stagger-in"
                style={{ animationDelay: `${idx * 55}ms` }}
              >
                <CourseCard
                  course={course}
                  materialCount={course.material_count ?? 0}
                  onUpdated={refetch}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <CreateCourseModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => refetch()}
      />
      <ImportTimetableModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => refetch()}
      />
    </div>
  );
}
