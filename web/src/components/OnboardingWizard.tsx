import { useState } from "react";
import type { OrgModel } from "../lib/api";

const STEPS = [
  { id: 0, title: "Проект", text: "Откройте свой лог или демо на открытых данных — сет не вшит в продукт." },
  { id: 1, title: "Аудит", text: "Смотрите иерархию/покрывало и красные зоны." },
  { id: 2, title: "Поток и нагрузка", text: "Срезы ×1/×2, стрелки передач и сценарии исключения." },
];

export function OnboardingWizard({
  model,
  onDone,
}: {
  model: OrgModel | null;
  onDone: () => void;
}) {
  const [step, setStep] = useState(0);
  const [open, setOpen] = useState(() => !localStorage.getItem("orgtwin_onboarded"));

  if (!open) return null;
  const s = STEPS[step];

  return (
    <div className="onboard-card">
      <strong>
        Онбординг {step + 1}/{STEPS.length}: {s.title}
      </strong>
      <p className="muted">{s.text}</p>
      {model?.honesty && step === 1 && (
        <ul className="muted" style={{ fontSize: 12 }}>
          {(model.honesty.proven || []).slice(0, 3).map((x) => (
            <li key={x}>✓ {x}</li>
          ))}
          {(model.honesty.not_proven || []).slice(0, 2).map((x) => (
            <li key={x}>○ ещё нет: {x}</li>
          ))}
        </ul>
      )}
      <div className="inspect-actions">
        {step < STEPS.length - 1 ? (
          <button type="button" className="btn" onClick={() => setStep((x) => x + 1)}>
            Дальше
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            onClick={() => {
              localStorage.setItem("orgtwin_onboarded", "1");
              setOpen(false);
              onDone();
            }}
          >
            Готово
          </button>
        )}
        <button
          type="button"
          className="btn ghost"
          onClick={() => {
            localStorage.setItem("orgtwin_onboarded", "1");
            setOpen(false);
          }}
        >
          Пропустить
        </button>
      </div>
    </div>
  );
}
