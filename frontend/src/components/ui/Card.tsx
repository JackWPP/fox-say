import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: "none" | "sm" | "md" | "lg";
  shadow?: "none" | "subtle" | "soft" | "md" | "lg";
  border?: boolean;
}

const paddingClasses: Record<NonNullable<CardProps["padding"]>, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-5",
  lg: "p-7"
};

const shadowClasses: Record<NonNullable<CardProps["shadow"]>, string> = {
  none: "",
  subtle: "shadow-subtle",
  soft: "shadow-soft",
  md: "shadow-md",
  lg: "shadow-lg"
};

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className = "", padding = "md", shadow = "soft", border = true, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={[
          "bg-white rounded-xl",
          paddingClasses[padding],
          shadowClasses[shadow],
          border ? "border border-slate-100" : "",
          className
        ].join(" ")}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = "Card";
