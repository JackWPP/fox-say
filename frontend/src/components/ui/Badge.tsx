import React from "react";

type BadgeVariant = "default" | "amber" | "success" | "warning" | "error" | "info";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: "sm" | "md";
}

const variantClasses: Record<BadgeVariant, string> = {
  default:
    "bg-slate-100 text-slate-700 border-slate-200",
  amber:
    "bg-foxAmber/15 text-amber-700 border-foxAmber/25",
  success:
    "bg-success/12 text-green-700 border-success/25",
  warning:
    "bg-foxAmber/15 text-amber-700 border-foxAmber/25",
  error:
    "bg-error/12 text-red-700 border-error/25",
  info:
    "bg-info/12 text-blue-700 border-info/25"
};

const sizeClasses: Record<NonNullable<BadgeProps["size"]>, string> = {
  sm: "px-2 py-0.5 text-xs rounded-md",
  md: "px-2.5 py-1 text-xs rounded-lg"
};

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className = "", variant = "default", size = "md", children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={[
          "inline-flex items-center font-medium border",
          variantClasses[variant],
          sizeClasses[size],
          className
        ].join(" ")}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = "Badge";
