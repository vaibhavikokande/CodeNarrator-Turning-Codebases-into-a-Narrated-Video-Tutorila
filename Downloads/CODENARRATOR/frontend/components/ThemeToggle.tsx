"use client";
/**
 * ThemeToggle — Sun / Moon button (ADDITIVE, standalone component).
 * Drop into any navbar — reads and writes theme via ThemeProvider context.
 */

import { useTheme } from "./ThemeProvider";

export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isLight = theme === "light";

  return (
    <button
      onClick={toggle}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
      title={isLight ? "Switch to dark mode" : "Switch to light mode"}
      style={{
        display:        "flex",
        alignItems:     "center",
        justifyContent: "center",
        width:          34,
        height:         34,
        borderRadius:   9,
        border:         `1px solid ${isLight ? "#c8d0f0" : "#252540"}`,
        background:     isLight ? "#e8eeff" : "#141428",
        cursor:         "pointer",
        fontSize:       17,
        transition:     "all .2s",
        flexShrink:     0,
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = "#6366f180";
        e.currentTarget.style.background  = isLight ? "#dce4ff" : "#1e1e38";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = isLight ? "#c8d0f0" : "#252540";
        e.currentTarget.style.background  = isLight ? "#e8eeff" : "#141428";
      }}
    >
      {isLight ? "🌙" : "☀️"}
    </button>
  );
}
