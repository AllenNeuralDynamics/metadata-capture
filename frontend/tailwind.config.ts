import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        // Anthropic brand colors
        brand: {
          magenta: {
            100: "#FBF0EC",
            200: "#F5D5C8",
            300: "#EEB99A",
            500: "#D97757",
            600: "#B5603F",
            800: "#6B3520",
            900: "#3A1A0F",
          },
          aqua: {
            400: "#4DC49C",
            500: "#24B283",
            700: "#0E6B54",
          },
          violet: {
            500: "#6258D1",
            600: "#4D44AB",
          },
          orange: {
            100: "#FAEFEB",
            500: "#E86235",
            600: "#BA4C27",
          },
          coral: "#F5E0D8",
          fig: "#D97757",
        },
        // Anthropic neutrals
        sand: {
          50: "#FAF9F7",
          100: "#F5F3EF",
          200: "#E8E6DC",
          300: "#D4D1C7",
          400: "#ADAAA0",
          500: "#87867F",
          600: "#5C5B56",
          700: "#3D3D3A",
          800: "#2A2A28",
          900: "#1A1A19",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        mono: ['"JetBrains Mono"', "Menlo", "Monaco", "monospace"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
export default config;
