import type { DonorInfo } from "../lib/api";
import { UploadPanel } from "./UploadPanel";

const LAST_KEY = "orgtwin-last-project";

export function rememberProject(id: string) {
  try {
    localStorage.setItem(LAST_KEY, id);
  } catch {
    /* ignore */
  }
}

export function readLastProject(): string | null {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}

/** Стартовый браузер сетов (как Ableton Set): инструмент пустой, проекты отдельно. */
export function ProjectBrowser({
  donors,
  onOpen,
  onUploaded,
  onRefresh,
}: {
  donors: DonorInfo[];
  onOpen: (id: string) => void;
  onUploaded: (id: string) => void;
  onRefresh: () => void;
}) {
  const demos = donors.filter((d) => d.demo || d.kind === "demo" || d.origin === "builtin");
  const mine = donors.filter((d) => !(d.demo || d.kind === "demo" || d.origin === "builtin"));

  return (
    <div className="project-browser">
      <header className="project-browser-head">
        <div>
          <div className="brand">
            Org<span>Twin</span>
          </div>
          <h1>Выберите проект</h1>
          <p className="muted">
            OrgTwin — пустой инструмент. Сет (проект) открывается отдельно: свой лог или демо на
            открытых данных. Как Set в Ableton — не «вшитая» часть продукта.
          </p>
        </div>
        <div className="project-browser-actions">
          <UploadPanel
            onUploaded={(id) => {
              onRefresh();
              onUploaded(id);
            }}
          />
          <button type="button" className="btn ghost" onClick={onRefresh} title="Обновить список">
            Обновить
          </button>
        </div>
      </header>

      <section className="project-section">
        <h2>Мои проекты</h2>
        <p className="muted section-hint">Загрузки CSV/XES и greenfield-черновики.</p>
        {mine.length === 0 ? (
          <div className="project-empty">
            Пока пусто. Загрузите свой лог («Свой CSV/XES») — появится здесь.
          </div>
        ) : (
          <ul className="project-grid">
            {mine.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  className="project-card"
                  disabled={!d.available}
                  onClick={() => onOpen(d.id)}
                >
                  <span className="project-badge project">{d.badge || "Проект"}</span>
                  <strong>{d.label}</strong>
                  <span className="muted">{d.subtitle || d.origin || ""}</span>
                  {!d.available && <span className="danger-text">файл недоступен</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="project-section">
        <h2>Демо · открытые данные</h2>
        <p className="muted section-hint">
          Учебные публичные логи (BPIC / Hospital). Это не данные заказчика и не «встроенный
          бизнес» OrgTwin — только для показа механики.
        </p>
        <ul className="project-grid">
          {demos.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                className="project-card demo"
                disabled={!d.available}
                onClick={() => onOpen(d.id)}
              >
                <span className="project-badge demo">{d.badge || "Демо"}</span>
                <strong>{d.label}</strong>
                <span className="muted">{d.subtitle || "Открытые учебные данные"}</span>
                {!d.available && <span className="danger-text">нет файла в data/raw</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
