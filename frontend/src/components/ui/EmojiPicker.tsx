import { useState } from "react";

const EMOJI_CATEGORIES: { label: string; emojis: string[] }[] = [
  {
    label: "学习",
    emojis: ["📚", "📖", "📝", "✏️", "🔬", "🔭", "🧪", "🧬", "💡", "🧠", "📐", "📏", "🖊️", "📓", "📔", "📒", "📕", "📗", "📘", "📙"],
  },
  {
    label: "理工",
    emojis: ["⚗️", "🔋", "💻", "🖥️", "⚙️", "🔧", "🔩", "🧲", "📡", "🛰️", "🤖", "🧮", "📊", "📈", "📉", "🗂️", "🗃️", "💾", "🖱️", "⌨️"],
  },
  {
    label: "文艺",
    emojis: ["🎨", "🎭", "🎬", "🎵", "🎸", "🎹", "🎺", "🎻", "🥁", "🎤", "📜", "✍️", "🖋️", "📰", "📷", "🎞️", "🎙️", "🎧", "📣", "🗣️"],
  },
  {
    label: "生活",
    emojis: ["🌍", "🌱", "🌿", "🍀", "🌸", "🌺", "🏔️", "🌊", "☀️", "⭐", "🌙", "🏠", "🚀", "✈️", "🚂", "🏆", "🎯", "🎲", "🎮", "🃏"],
  },
  {
    label: "动物",
    emojis: ["🦊", "🐼", "🐸", "🦁", "🐯", "🐻", "🐺", "🦝", "🐧", "🦉", "🦅", "🐬", "🐙", "🦋", "🐝", "🦄", "🐉", "🦖", "🦕", "🐲"],
  },
];

interface EmojiPickerProps {
  value: string;
  onChange: (emoji: string) => void;
}

export default function EmojiPicker({ value, onChange }: EmojiPickerProps) {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <div className="w-full">
      {/* Current selection */}
      <div className="flex items-center gap-3 mb-3">
        <div className="w-14 h-14 rounded-2xl bg-amber-50 border-2 border-amber-200 flex items-center justify-center text-3xl shadow-subtle select-none">
          {value}
        </div>
        <span className="text-sm text-slate-500">已选图标</span>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 mb-2 overflow-x-auto pb-1">
        {EMOJI_CATEGORIES.map((cat, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActiveTab(i)}
            className={`shrink-0 px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              activeTab === i
                ? "bg-foxAmber text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Emoji grid */}
      <div className="grid grid-cols-10 gap-0.5 bg-slate-50 rounded-xl p-2 border border-slate-100">
        {EMOJI_CATEGORIES[activeTab].emojis.map((emoji) => (
          <button
            key={emoji}
            type="button"
            onClick={() => onChange(emoji)}
            className={`w-8 h-8 rounded-lg flex items-center justify-center text-lg transition-all hover:scale-125 hover:bg-amber-100 ${
              value === emoji ? "bg-amber-200 ring-2 ring-foxAmber" : ""
            }`}
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  );
}
