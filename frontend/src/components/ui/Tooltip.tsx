import React from "react";

type TooltipPosition = "top" | "bottom" | "left" | "right";

export interface TooltipProps {
  content: React.ReactNode;
  position?: TooltipPosition;
  delay?: number;
  children: React.ReactNode;
  className?: string;
}

const positionClasses: Record<TooltipPosition, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2"
};

const arrowPositionClasses: Record<TooltipPosition, string> = {
  top: "top-full left-1/2 -translate-x-1/2 border-t-midnightCharcoal border-l-transparent border-r-transparent border-b-transparent",
  bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-midnightCharcoal border-l-transparent border-r-transparent border-t-transparent",
  left: "left-full top-1/2 -translate-y-1/2 border-l-midnightCharcoal border-t-transparent border-b-transparent border-r-transparent",
  right: "right-full top-1/2 -translate-y-1/2 border-r-midnightCharcoal border-t-transparent border-b-transparent border-l-transparent"
};

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  position = "top",
  children,
  className = ""
}) => {
  return (
    <span className={["relative inline-flex group", className].join(" ")}>
      {children}
      <span
        className={[
          "absolute z-50 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap",
          "bg-midnightCharcoal text-warmWhite shadow-soft",
          "opacity-0 scale-95 pointer-events-none",
          "group-hover:opacity-100 group-hover:scale-100",
          "transition-all duration-150 ease-out",
          positionClasses[position]
        ].join(" ")}
      >
        {content}
        <span
          className={[
            "absolute w-0 h-0 border-4",
            arrowPositionClasses[position]
          ].join(" ")}
        />
      </span>
    </span>
  );
};
