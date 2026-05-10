import { useState, useRef } from "react";
import { X, Upload, FileText, CheckCircle } from "lucide-react";
import { useImportTimetable } from "./useCourses";

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={handleClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-midnightCharcoal">导入课程表</h2>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 hover:border-foxAmber rounded-xl p-8 text-center cursor-pointer transition-colors mb-4"
        >
          <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
          {file ? (
            <div className="flex items-center justify-center gap-2 text-sm text-midnightCharcoal">
              <FileText className="w-4 h-4" />
              <span className="font-medium">{file.name}</span>
            </div>
          ) : (
            <p className="text-sm text-gray-500">拖拽 CSV 文件到此处，或点击选择</p>
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
          <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 rounded-lg p-3 mb-4">
            <CheckCircle className="w-4 h-4" />
            <span>成功导入 {result.imported} 门课程</span>
          </div>
        )}

        {error && (
          <p className="text-sm text-red-500 mb-4">{error}</p>
        )}

        <button
          onClick={handleSubmit}
          disabled={loading || !file}
          className="w-full py-2.5 bg-foxAmber hover:bg-foxAmber/90 disabled:bg-gray-300 text-midnightCharcoal font-semibold rounded-lg transition-colors"
        >
          {loading ? "导入中..." : "开始导入"}
        </button>
      </div>
    </div>
  );
}
