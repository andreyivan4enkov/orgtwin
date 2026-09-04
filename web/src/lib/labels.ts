/** Русские подписи UI (id агентов/активностей из лога не переводим). */

export const ORIGIN_RU: Record<string, string> = {
  log: "из лога",
  manual: "вручную",
  hybrid: "смешанный",
  builtin: "демо · открытые данные",
  upload: "ваш файл",
  greenfield: "черновик без лога",
};

export const MODE_HINT: Record<string, string> = {
  audit: "Оргсхема: организация → подразделения → сотрудники. Красное — затор.",
  flow: "Передачи дел (стрелки) и очереди (цвет/цифры). Срезы ×1/×2 — в панели наблюдения. Клик — пояснение.",
  stress: "То же, что «Поток»: передачи + нагрузка.",
  design: "Ручная правка ролей, сотрудников, слотов и связей. Пунктир — допущение, не факт лога.",
};

export const SLICE_RU: Record<
  string,
  { short: string; title: string; hint: string }
> = {
  x1: {
    short: "×1",
    title: "Обычная нагрузка",
    hint: "Поток как в логе (базовый срез очередей).",
  },
  x2: {
    short: "×2",
    title: "Двойной поток",
    hint: "Тот же процесс, но входящих кейсов вдвое больше — где растут очереди.",
  },
  x2_plus1: {
    short: "×2+1",
    title: "Двойной поток + слот",
    hint: "Как ×2, но узкому сотруднику добавлен ещё один слот занятости.",
  },
};

export function originLabel(origin: string | undefined): string {
  if (!origin) return "из лога";
  return ORIGIN_RU[origin] ?? origin;
}
