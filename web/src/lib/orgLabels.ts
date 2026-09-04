/** Человекочитаемые названия подразделений (восстановлены из лога). */

const BPIC2012: Record<string, { title: string; what: string }> = {
  APPLICATION: {
    title: "Отдел заявок",
    what: "Оформление и ведение кредитных заявок (события A_*)",
  },
  OFFER: {
    title: "Отдел предложений",
    what: "Оферты клиенту (события O_*)",
  },
  WORKITEM: {
    title: "Исполнение задач",
    what: "Рабочие задания по заявке (события W_*)",
  },
  UNKNOWN: { title: "Без подразделения", what: "Не удалось отнести к типу работ" },
};

const PROCUREMENT: Record<string, { title: string; what: string }> = {
  PR: { title: "Заявки на закупку", what: "Purchase requisition" },
  PO: { title: "Заказы поставщикам", what: "Purchase order" },
  GR: { title: "Приёмка", what: "Goods / service receipt" },
  INV: { title: "Счета и оплата", what: "Invoice / payment" },
  CONF: { title: "Подтверждения", what: "Order confirmation" },
  OTHER: { title: "Прочие закупки", what: "Остальные шаги закупочного цикла" },
  UNKNOWN: { title: "Без подразделения", what: "Не удалось отнести" },
};

/** org:group из Hospital_log — оригинал из таблицы + пояснение по-русски. */
const HOSPITAL_GROUPS: Record<string, { title: string; what: string }> = {
  "General Lab Clinical Chemistry": {
    title: "General Lab Clinical Chemistry",
    what: "Общая лаборатория клинической химии",
  },
  "Nursing ward": {
    title: "Nursing ward",
    what: "Сестринское / палатное отделение",
  },
  "Obstetrics & Gynaecology clinic": {
    title: "Obstetrics & Gynaecology clinic",
    what: "Клиника акушерства и гинекологии",
  },
  "Medical Microbiology": {
    title: "Medical Microbiology",
    what: "Медицинская микробиология",
  },
  Radiology: {
    title: "Radiology",
    what: "Рентгенология / лучевая диагностика",
  },
  Radiotherapy: {
    title: "Radiotherapy",
    what: "Лучевая терапия",
  },
  "Internal Specialisms clinic": {
    title: "Internal Specialisms clinic",
    what: "Клиника внутренних специализаций (терапия)",
  },
  Pathology: {
    title: "Pathology",
    what: "Патологиялогическая анатомия",
  },
  "Operating rooms": {
    title: "Operating rooms",
    what: "Операционные",
  },
  "Pharmacy Laboratory": {
    title: "Pharmacy Laboratory",
    what: "Аптечная лаборатория",
  },
  "Recovery room / high care": {
    title: "Recovery room / high care",
    what: "Палата пробуждения / высокоинтенсивный уход",
  },
  "Nuclear Medicine": {
    title: "Nuclear Medicine",
    what: "Ядерная медицина",
  },
  "Special lab radiology": {
    title: "Special lab radiology",
    what: "Специализированная радиологическая лаборатория",
  },
  "Diet Studies": {
    title: "Diet Studies",
    what: "Диетология / исследования питания",
  },
  "ICU Adults": {
    title: "ICU Adults",
    what: "Реанимация взрослых (ОРИТ)",
  },
  "Cardiovascular clinics": {
    title: "Cardiovascular clinics",
    what: "Кардиоваскулярные клиники",
  },
  "Hyper Pressure Tank": {
    title: "Hyper Pressure Tank",
    what: "Барокамера (гипербарическая оксигенация)",
  },
  "Day Centre - ward": {
    title: "Day Centre - ward",
    what: "Дневной стационар — палаты",
  },
  "Day Centre - treatment": {
    title: "Day Centre - treatment",
    what: "Дневной стационар — лечение",
  },
  "Anesthesiology clinic": {
    title: "Anesthesiology clinic",
    what: "Клиника анестезиологии",
  },
  "Pain clinic": {
    title: "Pain clinic",
    what: "Клиника боли",
  },
  Endoscopy: {
    title: "Endoscopy",
    what: "Эндоскопия",
  },
  "Third party lab": {
    title: "Third party lab",
    what: "Внешняя (сторонняя) лаборатория",
  },
  "Function Centre ENT": {
    title: "Function Centre ENT",
    what: "Функциональный центр ЛОР",
  },
  "Maternity ward": {
    title: "Maternity ward",
    what: "Родильное отделение",
  },
  "Special lab Nuro sensory": {
    title: "Special lab Nuro sensory",
    what: "Спецлаборатория нейросенсорики (как в логе)",
  },
  "Emergency room": {
    title: "Emergency room",
    what: "Приёмное / неотложная помощь",
  },
  Anesthesiology: {
    title: "Anesthesiology",
    what: "Анестезиология",
  },
  "IVF clinic": {
    title: "IVF clinic",
    what: "Клиника ЭКО",
  },
  "Lab Hematology": {
    title: "Lab Hematology",
    what: "Лаборатория гематологии",
  },
  "Lab Experimental Immunology": {
    title: "Lab Experimental Immunology",
    what: "Лаборатория экспериментальной иммунологии",
  },
  "surgery & urology clinic": {
    title: "surgery & urology clinic",
    what: "Клиника хирургии и урологии",
  },
  "Subsection nephrology": {
    title: "Subsection nephrology",
    what: "Подотдел нефрологии",
  },
  "Lung Function Study": {
    title: "Lung Function Study",
    what: "Исследование функции лёгких",
  },
  "Cardiology clinic": {
    title: "Cardiology clinic",
    what: "Кардиологическая клиника",
  },
  "Oral and Maxillofacial Surgery clinic": {
    title: "Oral and Maxillofacial Surgery clinic",
    what: "Клиника челюстно-лицевой хирургии",
  },
  "Special lab Genetic Metabolic Diseases": {
    title: "Special lab Genetic Metabolic Diseases",
    what: "Спецлаборатория генетических метаболических болезней",
  },
  "Ophthalmology clinic": {
    title: "Ophthalmology clinic",
    what: "Офтальмологическая клиника",
  },
  "Clinical Neurophysiology": {
    title: "Clinical Neurophysiology",
    what: "Клиническая нейрофизиология",
  },
  "subsection clinical immunology & rheumatology": {
    title: "subsection clinical immunology & rheumatology",
    what: "Подотдел клинической иммунологии и ревматологии",
  },
  LabVascularMedicine: {
    title: "LabVascular Medicine",
    what: "Лаборатория сосудистой медицины",
  },
  "LabVascular Medicine": {
    title: "LabVascular Medicine",
    what: "Лаборатория сосудистой медицины",
  },
  "Subsection infectious deceases, tropical & AIDS": {
    title: "Subsection infectious deceases, tropical & AIDS",
    what: "Подотдел инфекций, тропических болезней и СПИД (орфография лога)",
  },
  UNKNOWN: {
    title: "UNKNOWN",
    what: "Группа без названия в журнале",
  },
};

/**
 * Specialism code из Hospital_log — в таблице только число.
 * title: оригинал (код + доминирующие org:group из лога);
 * what: пояснение по-русски.
 */
const HOSPITAL_SPECIALISM: Record<string, { title: string; what: string }> = {
  "0": { title: "Specialism 0 (UNKNOWN)", what: "Код без опознанной клинической группы" },
  "2": {
    title: "Specialism 2 — Function Centre ENT",
    what: "Функциональный центр ЛОР",
  },
  "3": {
    title: "Specialism 3 — Hyper Pressure Tank",
    what: "Барокамера / гипербарическая оксигенация",
  },
  "5": {
    title: "Specialism 5 — Cardiology clinic",
    what: "Кардиология",
  },
  "6": {
    title: "Specialism 6 — surgery & urology / Endoscopy",
    what: "Хирургия, урология, эндоскопия",
  },
  "7": {
    title: "Specialism 7 — Nursing ward / Obstetrics & Gynaecology",
    what: "Палаты, акушерство и гинекология, операционные",
  },
  "13": {
    title: "Specialism 13 — Internal Specialisms clinic",
    what: "Внутренние болезни / терапия",
  },
  "18": {
    title: "Specialism 18 — Endoscopy",
    what: "Эндоскопия",
  },
  "20": {
    title: "Specialism 20 — Cardiovascular clinics",
    what: "Кардиоваскулярные направления",
  },
  "22": {
    title: "Specialism 22 — Nursing / ICU / Lung Function",
    what: "Палаты, реанимация, функция лёгких",
  },
  "24": {
    title: "Specialism 24 — clinical immunology & rheumatology",
    what: "Клиническая иммунология и ревматология",
  },
  "27": { title: "Specialism 27 (UNKNOWN)", what: "Код без опознанной группы" },
  "28": {
    title: "Specialism 28 — ICU Adults",
    what: "Реанимация взрослых",
  },
  "29": {
    title: "Specialism 29 — Obstetrics & Gynaecology",
    what: "Акушерство и гинекология",
  },
  "30": {
    title: "Specialism 30 — Nursing / Clinical Neurophysiology",
    what: "Палаты / клиническая нейрофизиология",
  },
  "50": {
    title: "Specialism 50 — Oral and Maxillofacial Surgery",
    what: "Челюстно-лицевая хирургия",
  },
  "61": {
    title: "Specialism 61 — Radiotherapy",
    what: "Лучевая терапия",
  },
  "62": {
    title: "Specialism 62 — Radiology",
    what: "Рентгенология / лучевая диагностика",
  },
  "63": {
    title: "Specialism 63 — Nuclear Medicine",
    what: "Ядерная медицина",
  },
  "86": {
    title: "Specialism 86 — General Lab Clinical Chemistry",
    what: "Клиническая химия и смежные лаборатории",
  },
  "87": {
    title: "Specialism 87 — Medical Microbiology",
    what: "Медицинская микробиология",
  },
  "88": {
    title: "Specialism 88 — Pathology",
    what: "Патологиялогическая анатомия",
  },
  "89": {
    title: "Specialism 89 — Recovery / ICU / Anesthesiology / Pain",
    what: "Пробуждение, реанимация, анестезиология, клиника боли",
  },
  "90": {
    title: "Specialism 90 — Genetic Metabolic Diseases lab",
    what: "Лаборатория генетических метаболических болезней",
  },
  "99": {
    title: "Specialism 99 — Diet Studies",
    what: "Диетология",
  },
};

const DONOR_ORG: Record<
  string,
  { company: string; structureNote: string; roleMode: string }
> = {
  BPIC2012: {
    company: "Кредитная организация (демо)",
    structureNote:
      "Подразделения не из HR: восстановлены по типу работ в журнале (заявки / предложения / исполнение).",
    roleMode: "activity_prefix",
  },
  BPIC2019: {
    company: "Закупки (демо BPIC2019)",
    structureNote:
      "Подразделения восстановлены по этапу закупочного цикла в журнале, не из штатного расписания.",
    roleMode: "procurement",
  },
  HOSPITAL2011: {
    company: "Больница (демо)",
    structureNote:
      "В журнале: org:group — оригинальные названия отделений (англ.); Specialism code — числовой код специализации. На схеме: оригинал + пояснение по-русски.",
    roleMode: "specialism",
  },
};

export function donorOrgMeta(donorId: string) {
  return (
    DONOR_ORG[donorId] || {
      company: donorId,
      structureNote:
        "Структура восстановлена из журнала событий: кто чем занят. Это не штатка из кадровой системы.",
      roleMode: "unknown",
    }
  );
}

export function roleTitle(roleId: string, donorId: string): string {
  if (donorId === "BPIC2012" && BPIC2012[roleId]) return BPIC2012[roleId].title;
  if (donorId === "BPIC2019" && PROCUREMENT[roleId]) return PROCUREMENT[roleId].title;
  if (donorId === "HOSPITAL2011") {
    if (HOSPITAL_SPECIALISM[roleId]) return HOSPITAL_SPECIALISM[roleId].title;
    if (HOSPITAL_GROUPS[roleId]) return HOSPITAL_GROUPS[roleId].title;
    return `Specialism ${roleId}`;
  }
  if (BPIC2012[roleId]) return BPIC2012[roleId].title;
  if (PROCUREMENT[roleId]) return PROCUREMENT[roleId].title;
  return roleId === "manual" || roleId === "вручную" ? "Ручное подразделение" : `Подразделение «${roleId}»`;
}

export function roleWhat(roleId: string, donorId: string): string {
  if (donorId === "BPIC2012" && BPIC2012[roleId]) return BPIC2012[roleId].what;
  if (donorId === "BPIC2019" && PROCUREMENT[roleId]) return PROCUREMENT[roleId].what;
  if (donorId === "HOSPITAL2011") {
    if (HOSPITAL_SPECIALISM[roleId]) return HOSPITAL_SPECIALISM[roleId].what;
    if (HOSPITAL_GROUPS[roleId]) return HOSPITAL_GROUPS[roleId].what;
    return "Код специализации из колонки Specialism code журнала";
  }
  return "Группа сотрудников с похожим типом работ в журнале";
}

/** Для Hospital агент = org:group с именем из таблицы; иначе — сотрудник. */
export function agentTitle(agentId: string, donorId?: string): string {
  if (donorId === "HOSPITAL2011" || HOSPITAL_GROUPS[agentId]) {
    return HOSPITAL_GROUPS[agentId]?.title ?? agentId;
  }
  if (/^\d+$/.test(agentId)) return `Сотрудник №${agentId}`;
  return `Сотрудник ${agentId}`;
}

export function agentWhat(agentId: string, donorId?: string): string | null {
  if (donorId === "HOSPITAL2011" || HOSPITAL_GROUPS[agentId]) {
    return HOSPITAL_GROUPS[agentId]?.what ?? null;
  }
  return null;
}

export function agentShort(agentId: string, donorId?: string): string {
  if (donorId === "HOSPITAL2011" || HOSPITAL_GROUPS[agentId]) {
    const t = HOSPITAL_GROUPS[agentId]?.title ?? agentId;
    return t.length > 18 ? t.slice(0, 16) + "…" : t;
  }
  if (/^\d+$/.test(agentId)) return `№${agentId}`;
  return agentId.length > 8 ? agentId.slice(0, 7) + "…" : agentId;
}
