import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api, type DonorInfo, type Mode, type OrgModel, type WhatIfResult } from "./lib/api";
import type { SliceKey } from "./lib/layout";
import { SLICE_RU, originLabel } from "./lib/labels";
import { agentTitle, donorOrgMeta, roleTitle } from "./lib/orgLabels";
import {
  explainAgentProblem,
  explainRoleProblem,
  type ProblemExplain,
} from "./lib/problems";
import { AuditStage } from "./components/AuditStage";
import { FlowView } from "./components/FlowView";
import { DesignView } from "./components/DesignView";
import { InspectPanel } from "./components/InspectPanel";
import { ObserveBar } from "./components/ObserveBar";
import { ProblemPopup } from "./components/ProblemPopup";
import { WhatIfPanel, emptyWhatIf, type WhatIfState } from "./components/WhatIfPanel";
import { ProductTools } from "./components/ProductTools";
import { OnboardingWizard } from "./components/OnboardingWizard";
import { SnapshotPanel } from "./components/SnapshotPanel";
import { ProjectBrowser, readLastProject, rememberProject } from "./components/ProjectBrowser";
import { useTheme } from "./lib/theme";
import "./styles/app.css";

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "audit", label: "Аудит", hint: "Структура: иерархия или покрывало связей" },
  {
    id: "flow",
    label: "Поток",
    hint: "Передачи дел + очереди ×1/×2 — клик по сотруднику",
  },
  { id: "design", label: "Проект", hint: "Ручная правка структуры" },
];

export default function App() {
  const [donors, setDonors] = useState<DonorInfo[]>([]);
  const [donorId, setDonorId] = useState<string>("");
  const [pickingProject, setPickingProject] = useState(true);
  const [mode, setMode] = useState<Mode>("audit");
  const [model, setModel] = useState<OrgModel | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [buildPct, setBuildPct] = useState(0);
  const [buildStage, setBuildStage] = useState("");
  const [buildDetail, setBuildDetail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [slice, setSlice] = useState<SliceKey>("x1");
  const [whatIf, setWhatIf] = useState<WhatIfState>(emptyWhatIf());
  const [whatIfResult, setWhatIfResult] = useState<WhatIfResult | null>(null);
  const [showWhatIf, setShowWhatIf] = useState(false);
  const [problem, setProblem] = useState<ProblemExplain | null>(null);
  const [problemMinimized, setProblemMinimized] = useState(false);
  const [railW, setRailW] = useState(260);
  const [inspectW, setInspectW] = useState(320);
  const drag = useRef<"rail" | "inspect" | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    api
      .donors()
      .then((d) => {
        setDonors(d);
        const last = readLastProject();
        if (last && d.some((x) => x.id === last && x.available)) {
          setDonorId(last);
          setPickingProject(false);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  const load = useCallback(async (id: string, force = false) => {
    setLoading(true);
    setQueueLoading(false);
    setError(null);
    setSelectedId(null);
    setPlaying(false);
    setWhatIf(emptyWhatIf());
    setWhatIfResult(null);
    setProblem(null);
    setProblemMinimized(false);
    setBuildPct(force ? 1 : 5);
    setBuildStage(force ? "Запуск пересборки…" : "Загрузка модели…");
    setBuildDetail("");
    try {
      // быстрый путь: кэш без force
      if (!force) {
        try {
          const cached = await api.orgModel(id, { force: false, with_queue: true });
          if (cached?.agents?.length || cached?.roles?.length) {
            setModel(cached);
            setBuildPct(100);
            setBuildStage("Из кэша");
            setLoading(false);
            return;
          }
        } catch {
          /* дальше async build */
        }
      }

      const { job_id } = await api.startBuild(id, { force, with_queue: true });
      for (;;) {
        await new Promise((r) => setTimeout(r, 400));
        const st = await api.buildStatus(job_id);
        setBuildPct(st.pct);
        setBuildStage(st.stage);
        setBuildDetail(st.detail || "");
        if (st.status === "done") {
          if (st.model) setModel(st.model);
          else setModel(await api.orgModel(id, { force: false, with_queue: true }));
          setLoading(false);
          setBuildPct(100);
          return;
        }
        if (st.status === "error") {
          throw new Error(st.error || "Ошибка сборки");
        }
      }
    } catch (e) {
      setError(String(e));
      setModel(null);
      setLoading(false);
      setQueueLoading(false);
    }
  }, []);

  useEffect(() => {
    if (donorId && !pickingProject) void load(donorId);
  }, [donorId, pickingProject, load]);

  const openProject = useCallback((id: string) => {
    rememberProject(id);
    setDonorId(id);
    setPickingProject(false);
    setMode("audit");
  }, []);

  const currentDonor = donors.find((d) => d.id === donorId);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!drag.current) return;
      const rect = workspaceRef.current?.getBoundingClientRect();
      if (!rect) return;
      const maxRail = Math.min(420, Math.floor(rect.width * 0.38));
      const maxInspect = Math.min(460, Math.floor(rect.width * 0.42));
      if (drag.current === "rail") {
        setRailW(Math.min(maxRail, Math.max(200, Math.round(e.clientX - rect.left))));
      } else {
        setInspectW(Math.min(maxInspect, Math.max(260, Math.round(rect.right - e.clientX))));
      }
    };
    const onUp = () => {
      drag.current = null;
    };
    const onResize = () => {
      const rect = workspaceRef.current?.getBoundingClientRect();
      if (!rect) return;
      const maxRail = Math.min(420, Math.floor(rect.width * 0.38));
      const maxInspect = Math.min(460, Math.floor(rect.width * 0.42));
      setRailW((w) => Math.min(w, maxRail));
      setInspectW((w) => Math.min(w, maxInspect));
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  const queueSlice = whatIfResult?.scenario || model?.queue_slices?.[slice] || null;
  const hasQueue = !!model?.queue_slices;
  const orgMeta = donorOrgMeta(donorId);

  const viewModel = useMemo(() => {
    if (!model) return null;
    if (!whatIf.excludeAgents.length && !whatIf.excludeRoles.length) {
      return model;
    }
    const exA = new Set(whatIf.excludeAgents);
    const exR = new Set(whatIf.excludeRoles);
    const agents = model.agents.filter((a) => !exA.has(a.id) && !exR.has(a.role_id));
    const roles = model.roles
      .filter((r) => !exR.has(r.id))
      .map((r) => ({
        ...r,
        n_agents: agents.filter((a) => a.role_id === r.id).length,
      }));
    return { ...model, agents, roles };
  }, [model, whatIf.excludeAgents, whatIf.excludeRoles]);

  const railAgents = useMemo(
    () =>
      [...(viewModel?.agents || [])].sort((a, b) => b.n_events - a.n_events).slice(0, 40),
    [viewModel]
  );

  const onSelect = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      setProblemMinimized(false);
      if (!model || !id) {
        setProblem(null);
        return;
      }
      const agent = model.agents.find((a) => a.id === id);
      if (agent) {
        setProblem(explainAgentProblem(model, agent, queueSlice));
        return;
      }
      const role = model.roles.find((r) => r.id === id);
      if (role) setProblem(explainRoleProblem(model, role.id, queueSlice));
      else setProblem(null);
    },
    [model, queueSlice]
  );

  return (
    <div className="app-shell">
      {pickingProject ? (
        <>
          <header className="topbar">
            <div className="topbar-left">
              <div className="brand" title="Цифровой двойник операционного организма">
                Org<span>Twin</span>
              </div>
            </div>
            <div className="topbar-tools">
              <button
                type="button"
                className="btn ghost theme-toggle"
                title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
                onClick={toggleTheme}
              >
                {theme === "dark" ? "Светлая" : "Тёмная"}
              </button>
            </div>
          </header>
          <ProjectBrowser
            donors={donors}
            onOpen={openProject}
            onUploaded={(id) => {
              void api.donors().then(setDonors);
              openProject(id);
            }}
            onRefresh={() => void api.donors().then(setDonors)}
          />
        </>
      ) : (
        <>
      <header className="topbar">
        <div className="topbar-left">
          <div className="brand" title="Цифровой двойник операционного организма">
            Org<span>Twin</span>
          </div>
          <nav className="modes" aria-label="Режимы">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                className={`mode-btn${mode === m.id ? " active" : ""}`}
                title={m.hint}
                onClick={() => setMode(m.id)}
              >
                {m.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="topbar-tools">
          <button
            type="button"
            className="project-chip"
            title="Сменить проект (сет)"
            onClick={() => {
              setPickingProject(true);
              setModel(null);
              setSelectedId(null);
              setProblem(null);
            }}
          >
            <span className={`project-badge ${currentDonor?.demo ? "demo" : "project"}`}>
              {currentDonor?.badge || (currentDonor?.demo ? "Демо" : "Проект")}
            </span>
            <span className="project-chip-name">{currentDonor?.label || donorId}</span>
            <span className="muted">сменить</span>
          </button>
          <button
            type="button"
            className={`btn ghost${showWhatIf ? " active-outline" : ""}`}
            title="Сценарии без сотрудника / отдела и локальная нагрузка"
            onClick={() => setShowWhatIf((v) => !v)}
          >
            Что если
          </button>
          <button
            type="button"
            className="btn ghost"
            title="Заново собрать модель из лога"
            onClick={() => void load(donorId, true)}
          >
            Пересобрать
          </button>
          <button
            type="button"
            className="btn ghost theme-toggle"
            title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            aria-label={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
            onClick={toggleTheme}
          >
            {theme === "dark" ? "Светлая" : "Тёмная"}
          </button>
        </div>
      </header>

      <div className="subbar">
        <ObserveBar
          playing={playing}
          onPlayingChange={setPlaying}
          slice={slice}
          onSliceChange={setSlice}
          hasQueue={hasQueue}
          hint={
            queueLoading
              ? "Считаем очереди…"
              : "Красное = проблема. Клик — пояснение. Тяните границы панелей."
          }
        />
      </div>

      <div
        className="workspace"
        ref={workspaceRef}
        style={
          {
            gridTemplateColumns: `${railW}px 6px minmax(0, 1fr) 6px ${inspectW}px`,
          } as CSSProperties
        }
      >
        <aside className="rail">
          <h2>Организация</h2>
          {viewModel && (
            <>
              <div className="rail-org-name">{orgMeta.company}</div>
              <p className="muted rail-note">{orgMeta.structureNote}</p>
              <div className="muted" style={{ marginBottom: 13, fontSize: 12 }}>
                данные: {originLabel(viewModel.origin)}
                {model?.build_wall_sec != null && <> · собрано за {model.build_wall_sec} с</>}
              </div>
              <SnapshotPanel
                donorId={donorId}
                hasModel={!!model}
                onLoaded={(m) => {
                  setModel(m as OrgModel);
                  setError(null);
                }}
              />
              <h2>Подразделения</h2>
              <ul className="rail-list">
                {viewModel.roles.slice(0, 20).map((r) => (
                  <li
                    key={r.id}
                    className={`rail-item${selectedId === r.id ? " selected" : ""}`}
                    onClick={() => onSelect(r.id)}
                  >
                    <span>{roleTitle(r.id, viewModel.donor_id)}</span>
                    <span className="mono muted">{r.n_agents}</span>
                  </li>
                ))}
              </ul>
              <h2 style={{ marginTop: 21 }}>Сотрудники</h2>
              <ul className="rail-list">
                {railAgents.map((a) => (
                  <li
                    key={a.id}
                    className={`rail-item${selectedId === a.id ? " selected" : ""}`}
                    onClick={() => onSelect(a.id)}
                  >
                    <span>{agentTitle(a.id, viewModel.donor_id)}</span>
                    <span className="mono muted">{a.n_events}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>

        <div
          className="splitter"
          title="Тяните, чтобы изменить ширину"
          onMouseDown={() => {
            drag.current = "rail";
          }}
        />

        <main className="stage">
          {loading && (
            <div className="status-banner build-progress">
              <div className="build-progress-head">
                <strong>{buildPct}%</strong>
                <span>{buildStage || "Сборка…"}</span>
              </div>
              <div className="build-bar">
                <i style={{ width: `${Math.max(2, buildPct)}%` }} />
              </div>
              {buildDetail && <div className="muted build-detail">{buildDetail}</div>}
              <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                Не зависло: идут обучение политики и симуляция очередей — это может занять минуты.
              </div>
            </div>
          )}
          {queueLoading && !loading && <div className="status-banner">Досчитываем очереди…</div>}
          {error && <div className="error-banner">{error}</div>}
          {problem && (
            <div className={`problem-float${problemMinimized ? " is-chip" : ""}`}>
              <ProblemPopup
                explain={problem}
                minimized={problemMinimized}
                onToggleMinimize={() => setProblemMinimized((v) => !v)}
                onClose={() => {
                  setProblem(null);
                  setProblemMinimized(false);
                }}
                onWhatIf={() => {
                  setShowWhatIf(true);
                  setMode("flow");
                }}
              />
            </div>
          )}
          {!loading && !error && viewModel && mode === "audit" && (
            <AuditStage
              model={viewModel}
              selectedId={selectedId}
              onSelect={onSelect}
              queueSlice={queueSlice}
            />
          )}
          {!loading && !error && viewModel && (mode === "flow" || mode === "stress") && (
            <>
              <FlowView
                model={viewModel}
                slice={slice}
                queueSlice={queueSlice}
                playing={playing}
                selectedId={selectedId}
                onSelect={onSelect}
              />
              {showWhatIf && model && (
                <div className="whatif-dock">
                  <WhatIfPanel
                    donorId={donorId}
                    model={model}
                    state={whatIf}
                    onChange={setWhatIf}
                    result={whatIfResult}
                    onResult={setWhatIfResult}
                  />
                </div>
              )}
            </>
          )}
          {!loading && !error && model && mode === "design" && (
            <DesignView donorId={donorId} model={model} onSaved={() => void load(donorId, true)} />
          )}
          {showWhatIf && mode !== "flow" && mode !== "stress" && model && (
            <div className="whatif-dock overlay">
              <WhatIfPanel
                donorId={donorId}
                model={model}
                state={whatIf}
                onChange={setWhatIf}
                result={whatIfResult}
                onResult={setWhatIfResult}
              />
            </div>
          )}
        </main>

        <div
          className="splitter"
          title="Тяните, чтобы изменить ширину"
          onMouseDown={() => {
            drag.current = "inspect";
          }}
        />

        <div className="inspect-stack">
          <OnboardingWizard model={model} onDone={() => setMode("flow")} />
          {model && (
            <ProductTools
              model={model}
              donorId={donorId}
              onRefresh={() => void load(donorId, true)}
            />
          )}
          <InspectPanel
            model={viewModel}
            selectedId={selectedId}
            queueSlice={queueSlice}
            problem={problem && !problemMinimized ? problem : null}
            onShowProblem={
              selectedId && (!problem || problemMinimized)
                ? () => {
                    if (!model || !selectedId) return;
                    const agent = model.agents.find((a) => a.id === selectedId);
                    if (agent) {
                      setProblem(explainAgentProblem(model, agent, queueSlice));
                      setProblemMinimized(false);
                      return;
                    }
                    const role = model.roles.find((r) => r.id === selectedId);
                    if (role) {
                      setProblem(explainRoleProblem(model, role.id, queueSlice));
                      setProblemMinimized(false);
                    }
                  }
                : undefined
            }
            onExcludeAgent={(id) => {
              setWhatIf((s) => ({
                ...s,
                excludeAgents: s.excludeAgents.includes(id)
                  ? s.excludeAgents
                  : [...s.excludeAgents, id],
              }));
              setShowWhatIf(true);
            }}
            onExcludeRole={(id) => {
              setWhatIf((s) => ({
                ...s,
                excludeRoles: s.excludeRoles.includes(id)
                  ? s.excludeRoles
                  : [...s.excludeRoles, id],
              }));
              setShowWhatIf(true);
            }}
            onBoostRole={(id) => {
              setWhatIf((s) => ({
                ...s,
                roleMultipliers: { ...s.roleMultipliers, [id]: 2 },
                globalMultiplier: 1,
              }));
              setShowWhatIf(true);
              setMode("flow");
            }}
          />
        </div>
      </div>
        </>
      )}
    </div>
  );
}
