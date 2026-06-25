import React from "react";
import { User } from "lucide-react";

type AvatarVariant = "ai" | "user";
type AvatarSize = "sm" | "md" | "lg";

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: AvatarVariant;
  size?: AvatarSize;
}

const sizeClasses: Record<AvatarSize, string> = {
  sm: "w-7 h-7 text-sm",
  md: "w-9 h-9 text-base",
  lg: "w-11 h-11 text-lg"
};

const variantClasses: Record<AvatarVariant, string> = {
  ai: "bg-foxAmber/15 text-foxAmber",
  user: "bg-slate-200 text-slate-600"
};

export const Avatar: React.FC<AvatarProps> = ({
  variant = "ai",
  size = "md",
  className = "",
  ...props
}) => {
  return (
    <div
      className={[
        "rounded-full inline-flex items-center justify-center shrink-0",
        sizeClasses[size],
        variantClasses[variant],
        className
      ].join(" ")}
      {...props}
    >
      {variant === "ai" ? (
        <span className="leading-none">🦊</span>
      ) : (
        <User className="w-[60%] h-[60%]" strokeWidth={2} />
      )}
    </div>
  );
};
