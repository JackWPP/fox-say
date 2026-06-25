import { useState } from "react";
import { X, Save } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Textarea } from "../../components/ui/Textarea";

interface NoteEditorProps {
  courseId: string;
  onSave: (title: string, content: string) => Promise<void>;
  onCancel: () => void;
  initialTitle?: string;
  initialContent?: string;
}

export default function NoteEditor({ onSave, onCancel, initialTitle = "", initialContent = "" }: NoteEditorProps) {
  const [title, setTitle] = useState(initialTitle);
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await onSave(title.trim(), content.trim());
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
      <Input
        placeholder="笔记标题"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="h-9 text-sm"
        autoFocus
      />
      <Textarea
        placeholder="写点什么..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={4}
        className="text-sm resize-none"
      />
      <div className="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          <X className="w-3.5 h-3.5 mr-1" />
          取消
        </Button>
        <Button size="sm" onClick={handleSave} disabled={!title.trim() || saving}>
          <Save className="w-3.5 h-3.5 mr-1" />
          {saving ? "保存中..." : "保存"}
        </Button>
      </div>
    </div>
  );
}
