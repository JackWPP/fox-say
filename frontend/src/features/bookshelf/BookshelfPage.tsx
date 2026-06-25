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
    <div className="min-h-full p-6 md:p-10 bg-slate-50">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-start justify-between mb-10">
          <div>
            <h1 className="text-3xl font-bold text-midnightCharcoal tracking-tight">我的课程</h1>
            <p className="text-slate-500 mt-1.5 text-sm">管理你的课程和学习材料</p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={() => setImportOpen(true)}
            >
              <Table2 className="w-4 h-4" />
              导入课程表
            </Button>
            <Button
              variant="primary"
              onClick={() => setCreateOpen(true)}
            >
              <Plus className="w-4 h-4" />
              创建课程
            </Button>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-24">
            <Spinner size="lg" />
          </div>
        )}

        {error && (
          <div className="text-center py-24">
            <div className="text-5xl mb-4">😿</div>
            <p className="text-red-500 mb-4 font-medium">加载失败: {error}</p>
            <Button
              variant="secondary"
              onClick={refetch}
            >
              <RefreshCw className="w-4 h-4" />
              重试
            </Button>
          </div>
        )}

        {!loading && !error && courses.length === 0 && (
          <div className="text-center py-24">
            <div className="text-8xl mb-6">🦊</div>
            <p className="text-2xl font-bold text-midnightCharcoal mb-2">{foxCopy.bookshelf.empty}</p>
            <p className="text-slate-500 mb-8 max-w-md mx-auto">{foxCopy.bookshelf.emptyHint}</p>
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
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
            {courses.map((course) => (
              <CourseCard key={course.id} course={course} materialCount={course.material_count ?? 0} />
            ))}
          </div>
        )}

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
    </div>
  );
}
