import { useState, useRef } from "react";
import { X, Upload, FileText, CheckCircle } from "lucide-react";
import { useImportTimetable } from "./useCourses";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";

interface ImportTimetableModalProps {
  open: boolean;
  onClose: () => void;
  onImported: (courseIds: string[]) => void;
}

export default function ImportTimetableModal({ open, onClose, onImported }: ImportTimetableModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { importTimetable, loading, error, result } = useImportTimetable();

  if (!open) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.name.endsWith(".csv")) {
      setFile(dropped);
    }
  };

  const handleSubmit = async () => {
    if (!file) return;
    try {
      const data = await importTimetable(file);
      if (data) onImported(data.courses.map((c) => c.id));
    } catch {}
  };

  const handleClose = () => {
    setFile(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={handleClose}>
      <Card
        padding="lg"
        shadow="lg"
        className="w-full max-w-md mx-4 rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-midnightCharcoal">导入课程表</h2>
          <Button variant="icon" onClick={handleClose} className="h-8 w-8">
            <X className="w-5 h-5" />
          </Button>
        </div>

        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-slate-200 hover:border-foxAmber rounded-2xl p-10 text-center cursor-pointer transition-all duration-200 hover:bg-foxAmber/5 mb-5"
        >
          <div className="p-3 rounded-2xl bg-foxAmber/10 w-fit mx-auto mb-3">
            <Upload className="w-8 h-8 text-foxAmber" />
          </div>
          {file ? (
            <div className="flex items-center justify-center gap-2 text-sm text-midnightCharcoal font-medium">
              <FileText className="w-4 h-4 text-foxAmber" />
              <span>{file.name}</span>
            </div>
          ) : (
            <div>
              <p className="text-sm font-medium text-slate-700 mb-1">拖拽 CSV 文件到此处</p>
              <p className="text-xs text-slate-400">或点击选择文件</p>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>

        {result && (
          <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 rounded-xl p-4 mb-4 border border-green-200">
            <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
            <span className="font-medium">成功导入 {result.imported} 门课程</span>
          </div>
        )}

        {error && (
          <p className="text-sm text-red-500 bg-red-50 rounded-xl p-3 mb-4 border border-red-200">{error}</p>
        )}

        <Button
          onClick={handleSubmit}
          disabled={loading || !file}
          loading={loading}
          className="w-full rounded-xl h-11 text-base"
          size="lg"
        >
          {loading ? "导入中..." : "开始导入"}
        </Button>
      </Card>
    </div>
  );
}
