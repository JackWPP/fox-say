import React from "react";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className = "", error, disabled, rows = 3, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        disabled={disabled}
        rows={rows}
        className={[
          "w-full px-3.5 py-2.5 rounded-xl text-sm bg-white resize-y",
          "border transition-all duration-200 ease-out",
          "placeholder:text-slate-400",
          "leading-relaxed",
          error
            ? "border-error focus:border-error focus:ring-2 focus:ring-error/20"
            : "border-slate-200 hover:border-slate-300 focus:border-foxAmber focus:ring-2 focus:ring-foxAmber/20",
          "disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-slate-50",
          "outline-none",
          className
        ].join(" ")}
        {...props}
      />
    );
  }
);

Textarea.displayName = "Textarea";
