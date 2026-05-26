"use client";
/**
 * ThemeProvider — Dark / Light theme (ADDITIVE, standalone).
 *
 * • Reads preference from localStorage (key: "cn-theme")
 * • Falls back to OS preference (prefers-color-scheme)
 * • Applies   data-theme="dark" | data-theme="light"  on <html>
 * • Exports   useTheme()  hook for any component that needs to read the value
 *
 * Does NOT touch any existing component.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";

type Theme = "dark" | "light";

interface ThemeCtx {
  theme:     Theme;
  toggle:    () => void;
  setTheme:  (t: Theme) => void;
}

const ThemeContext = createContext<ThemeCtx>({
  theme:    "dark",
  toggle:   () => {},
  setTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}

// ── Anti-FOUC script injected into <head> ─────────────────────────────────
// This runs before React hydrates so the page never flashes the wrong theme.
export const themeScript = `(function(){
  try {
    var t = localStorage.getItem('cn-theme');
    if (!t) t = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
  } catch(e) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();`;

// ── Provider component ────────────────────────────────────────────────────
export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");

  // On mount: read saved preference or OS setting
  useEffect(() => {
    let saved = localStorage.getItem("cn-theme") as Theme | null;
    if (!saved) {
      saved = window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
    }
    setThemeState(saved);
    document.documentElement.setAttribute("data-theme", saved);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem("cn-theme", t);
    document.documentElement.setAttribute("data-theme", t);
  }, []);

  const toggle = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark");
  }, [theme, setTheme]);

  return (
    <ThemeContext.Provider value={{ theme, toggle, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
