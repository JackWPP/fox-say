import React from "react";
import { Check } from "lucide-react";

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
}

export const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className = "", label, id, checked, onChange, disabled, ...props }, ref) => {
    const inputId = id || React.useId();

    return (
      <label
        htmlFor={inputId}
        className={[
          "inline-flex items-center gap-2 cursor-pointer select-none",
          disabled ? "opacity-50 cursor-not-allowed" : "",
          className
        ].join(" ")}
      >
        <span className="relative inline-flex items-center justify-center">
          <input
            ref={ref}
            id={inputId}
            type="checkbox"
            checked={checked}
            onChange={onChange}
            disabled={disabled}
            className="peer sr-only"
            {...props}
          />
          <span
            className={[
              "w-5 h-5 rounded-md border-2 border-slate-300 bg-white",
              "transition-all duration-200 ease-out",
              "peer-checked:bg-foxAmber peer-checked:border-foxAmber",
              "peer-focus-visible:ring-2 peer-focus-visible:ring-foxAmber peer-focus-visible:ring-offset-1",
              "peer-disabled:opacity-50"
            ].join(" ")}
          >
            {checked && (
              <Check
                className="w-full h-full text-midnightCharcoal fox-check"
                strokeWidth={3}
              />
            )}
          </span>
        </span>
        {label && (
          <span className="text-sm text-slate-700">{label}</span>
        )}
      </label>
    );
  }
);

Checkbox.displayName = "Checkbox";
