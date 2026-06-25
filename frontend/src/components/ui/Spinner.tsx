import React from "react";

type SpinnerSize = "sm" | "md" | "lg";

export interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: SpinnerSize;
}

const sizeClasses: Record<SpinnerSize, string> = {
  sm: "w-4 h-4 border-2",
  md: "w-6 h-6 border-[2.5px]",
  lg: "w-10 h-10 border-[3px]"
};

export const Spinner: React.FC<SpinnerProps> = ({
  size = "md",
  className = "",
  ...props
}) => {
  return (
    <div
      className={[
        "animate-spin rounded-full",
        "border-foxAmber/25 border-t-foxAmber",
        sizeClasses[size],
        className
      ].join(" ")}
      {...props}
    />
  );
};
