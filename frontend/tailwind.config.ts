import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        foxAmber: "#F59E0B",
        midnightCharcoal: "#111317",
        warmWhite: "#FFF7ED",
        success: {
          DEFAULT: "#22C55E",
          600: "#16A34A"
        },
        error: {
          DEFAULT: "#EF4444",
          600: "#DC2626"
        },
        info: {
          DEFAULT: "#3B82F6",
          600: "#2563EB"
        }
      },
      boxShadow: {
        "subtle": "0 1px 2px rgba(0,0,0,0.04)",
        "soft": "0 2px 8px rgba(0,0,0,0.06)",
        "md": "0 4px 16px rgba(0,0,0,0.08)",
        "lg": "0 8px 32px rgba(0,0,0,0.1)"
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"PingFang SC"',
          '"Microsoft YaHei"',
          '"Segoe UI"',
          "Roboto",
          "sans-serif"
        ]
      },
      transitionTimingFunction: {
        "out": "cubic-bezier(0.2, 0.7, 0.2, 1)"
      }
    }
  },
  plugins: []
} satisfies Config;

