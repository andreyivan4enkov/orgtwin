import { useCallback, useEffect, useState } from "react";
import { initCanvasColors, syncCanvasColors } from "./tokens";

export type ThemeMode = "light" | "dark";

const STORAGE_KEY = "orgtwin-theme";

function readStored(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "dark" || v === "light") return v;
  } catch {
    /* ignore */
  }
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

export function applyTheme(theme: ThemeMode) {
  document.documentElement.setAttribute("data-theme", theme);
  syncCanvasColors(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}

/** Применить тему до первого paint (вызывать из main). */
export function initTheme(): ThemeMode {
  const theme = readStored();
  document.documentElement.setAttribute("data-theme", theme);
  syncCanvasColors(theme);
  initCanvasColors();
  return theme;
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() =>
    typeof document !== "undefined"
      ? ((document.documentElement.getAttribute("data-theme") as ThemeMode) || readStored())
      : "light"
  );

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  const setTheme = useCallback((t: ThemeMode) => setThemeState(t), []);

  return { theme, setTheme, toggleTheme, isDark: theme === "dark" };
}
