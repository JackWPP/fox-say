import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        foxAmber: "#F59E0B",
        midnightCharcoal: "#111317",
        warmWhite: "#FFF7ED"
      }
    }
  },
  plugins: []
} satisfies Config;

