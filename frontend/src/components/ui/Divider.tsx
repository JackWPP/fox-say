import React from "react";

export interface DividerProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: "horizontal" | "vertical";
  spacing?: "none" | "sm" | "md" | "lg";
}

const spacingClasses: Record<NonNullable<DividerProps["orientation"]>, Record<NonNullable<DividerProps["spacing"]>, string>> = {
  horizontal: {
    none: "my-0",
    sm: "my-3",
    md: "my-5",
    lg: "my-8"
  },
  vertical: {
    none: "mx-0",
    sm: "mx-3",
    md: "mx-5",
    lg: "mx-8"
  }
};

export const Divider: React.FC<DividerProps> = ({
  orientation = "horizontal",
  spacing = "md",
  className = "",
  ...props
}) => {
  const isHorizontal = orientation === "horizontal";
  return (
    <div
      role="separator"
      className={[
        isHorizontal ? "h-px w-full" : "w-px h-full",
        "bg-slate-200",
        spacingClasses[orientation][spacing],
        className
      ].join(" ")}
      {...props}
    />
  );
};
