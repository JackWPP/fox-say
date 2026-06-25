import React from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className = "", error, disabled, ...props }, ref) => {
    return (
      <input
        ref={ref}
        disabled={disabled}
        className={[
          "w-full h-10 px-3.5 rounded-xl text-sm bg-white",
          "border transition-all duration-200 ease-out",
          "placeholder:text-slate-400",
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

Input.displayName = "Input";
