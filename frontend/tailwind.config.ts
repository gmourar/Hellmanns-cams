import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        hellmanns: "#FFD200",
        navy: {
          DEFAULT: "#002D5E",
          light: "#003B7A",
        },
        ink: "#0A0A0A",
        flame: "#FF6B00",
        court: "#E8003D",
      },
      fontFamily: {
        display: ["var(--font-bebas)", "Impact", "sans-serif"],
        body: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      keyframes: {
        pulse_red: {
          "0%, 100%": { backgroundColor: "rgba(232,0,61,0.08)" },
          "50%": { backgroundColor: "rgba(232,0,61,0.22)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        spin_slow: {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        slide_up: {
          from: { transform: "translateY(100%)", opacity: "0" },
          to: { transform: "translateY(0)", opacity: "1" },
        },
        pop_in: {
          "0%": { transform: "scale(0.85)", opacity: "0" },
          "70%": { transform: "scale(1.04)" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
      animation: {
        pulse_red: "pulse_red 1.4s ease-in-out infinite",
        blink: "blink 1s step-start infinite",
        spin_slow: "spin_slow 3s linear infinite",
        slide_up: "slide_up 0.35s cubic-bezier(0.22,1,0.36,1) both",
        pop_in: "pop_in 0.45s cubic-bezier(0.22,1,0.36,1) both",
      },
    },
  },
  plugins: [],
};

export default config;
