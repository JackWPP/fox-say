import React from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "icon";
type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-foxAmber text-midnightCharcoal hover:bg-amber-500 active:bg-amber-600 shadow-soft",
  secondary:
    "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 hover:border-slate-300",
  ghost:
    "bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  icon:
    "bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900 rounded-full"
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm rounded-lg gap-1.5",
  md: "h-10 px-4 text-sm rounded-xl gap-2",
  lg: "h-12 px-6 text-base rounded-xl gap-2"
};

const iconSizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 w-8 rounded-lg",
  md: "h-10 w-10 rounded-xl",
  lg: "h-12 w-12 rounded-xl"
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = "", variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => {
    const isIcon = variant === "icon";
    const sizeCls = isIcon ? iconSizeClasses[size] : sizeClasses[size];

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={[
          "inline-flex items-center justify-center font-medium select-none",
          "transition-all duration-200 ease-out",
          "focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed",
          variantClasses[variant],
          sizeCls,
          className
        ].join(" ")}
        {...props}
      >
        {loading ? (
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70" />
        ) : (
          children
        )}
      </button>
    );
  }
);

Button.displayName = "Button";
