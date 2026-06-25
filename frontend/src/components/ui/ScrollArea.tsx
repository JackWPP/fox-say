import React from "react";

export interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  viewportClassName?: string;
}

export const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className = "", viewportClassName = "", children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={["relative overflow-hidden", className].join(" ")}
        {...props}
      >
        <div
          className={[
            "h-full w-full overflow-y-auto overflow-x-hidden",
            "fox-scroll",
            viewportClassName
          ].join(" ")}
        >
          {children}
        </div>
      </div>
    );
  }
);

ScrollArea.displayName = "ScrollArea";
