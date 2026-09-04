/** Hex-палитры для React Flow / canvas (CSS var в SVG тормозит). HTML берёт var(--*) из CSS. */

export type CanvasColors = {
  bg: string;
  surface: string;
  ink: string;
  inkMuted: string;
  line: string;
  accent: string;
  accentSoft: string;
  warn: string;
  warnSoft: string;
  danger: string;
  dangerSoft: string;
  info: string;
  infoSoft: string;
  inkSoft: string;
};

const LIGHT: CanvasColors = {
  bg: "#F7F6F3",
  surface: "#FFFFFF",
  ink: "#1C1B19",
  inkMuted: "#6B6860",
  line: "#E4E1D9",
  accent: "#0F6E56",
  accentSoft: "rgba(15, 110, 86, 0.18)",
  warn: "#B54708",
  warnSoft: "rgba(181, 71, 8, 0.15)",
  danger: "#A32D2D",
  dangerSoft: "rgba(163, 45, 45, 0.15)",
  info: "#2F5D8A",
  infoSoft: "rgba(47, 93, 138, 0.15)",
  inkSoft: "rgba(28, 27, 25, 0.12)",
};

const DARK: CanvasColors = {
  bg: "#141311",
  surface: "#1E1D1A",
  ink: "#F0EEE8",
  inkMuted: "#9A968C",
  line: "#2F2D28",
  accent: "#3D9B7A",
  accentSoft: "rgba(61, 155, 122, 0.22)",
  warn: "#E08A3C",
  warnSoft: "rgba(224, 138, 60, 0.2)",
  danger: "#E06A6A",
  dangerSoft: "rgba(224, 106, 106, 0.2)",
  info: "#6A9CC4",
  infoSoft: "rgba(106, 156, 196, 0.2)",
  inkSoft: "rgba(240, 238, 232, 0.1)",
};

let current: CanvasColors = LIGHT;

export function syncCanvasColors(theme: "light" | "dark") {
  current = theme === "dark" ? DARK : LIGHT;
}

export function initCanvasColors() {
  const t =
    typeof document !== "undefined"
      ? (document.documentElement.getAttribute("data-theme") as "light" | "dark" | null)
      : null;
  current = t === "dark" ? DARK : LIGHT;
}

/** Актуальные hex-цвета для графов (мутируемый объект — ссылка стабильна). */
export const tokens = {
  space: { 1: 8, 2: 13, 3: 21, 4: 34, 5: 55, 6: 89 },
  get colors() {
    return current;
  },
} as {
  space: { 1: number; 2: number; 3: number; 4: number; 5: number; 6: number };
  colors: CanvasColors;
};

export type EntityKind =
  | "org"
  | "role"
  | "agent"
  | "action"
  | "case"
  | "queue"
  | "slot"
  | "manual";

export const entityLegend: { kind: EntityKind; label: string; shape: string }[] = [
  { kind: "org", label: "Организация", shape: "блок сверху" },
  { kind: "role", label: "Подразделение", shape: "скруглённый прямоугольник" },
  { kind: "agent", label: "Сотрудник", shape: "круг" },
  { kind: "action", label: "Действие / правило", shape: "ромб" },
  { kind: "case", label: "Документ / кейс", shape: "лист" },
  { kind: "queue", label: "Очередь / затор", shape: "штрихи / красная обводка" },
  { kind: "slot", label: "Слот занятости", shape: "квадрат в круге" },
  { kind: "manual", label: "Ручная правка", shape: "пунктир" },
];
