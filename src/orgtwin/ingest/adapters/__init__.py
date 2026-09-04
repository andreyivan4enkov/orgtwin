"""
Адаптеры источников событий → плоская event table.

Контракт колонок: case:concept:name, concept:name, time:timestamp, agent[, context].
SQL / CRM / ERP — каркасы контракта (без живого коннектора в v1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import pandas as pd


REQUIRED = ("case:concept:name", "concept:name", "time:timestamp")


class EventSource(ABC):
    """
    Единый источник событий.

    load() — полный снимок; pull(fit_start, fit_end) — опциональное окно по времени.
    """

    @abstractmethod
    def load(self) -> pd.DataFrame:
        ...

    def pull(
        self,
        fit_start: Any | None = None,
        fit_end: Any | None = None,
    ) -> pd.DataFrame:
        """
        Выгрузка окна [fit_start, fit_end).
        Если границы не заданы — полный load().
        """
        df = self.load()
        if fit_start is None and fit_end is None:
            return df
        if "time:timestamp" not in df.columns:
            raise ValueError("pull: нет колонки time:timestamp")
        ts = pd.to_datetime(df["time:timestamp"], utc=True)
        mask = pd.Series(True, index=df.index)
        if fit_start is not None:
            start = pd.Timestamp(fit_start)
            if start.tzinfo is None:
                start = start.tz_localize("UTC")
            else:
                start = start.tz_convert("UTC")
            mask &= ts >= start
        if fit_end is not None:
            end = pd.Timestamp(fit_end)
            if end.tzinfo is None:
                end = end.tz_localize("UTC")
            else:
                end = end.tz_convert("UTC")
            mask &= ts < end
        return df.loc[mask].reset_index(drop=True)


# обратная совместимость
EventSourceAdapter = EventSource


class XesAdapter(EventSource):
    def __init__(self, path: str | Path, agent_col: str | None = None):
        self.path = Path(path)
        self.agent_col = agent_col

    def load(self) -> pd.DataFrame:
        from orgtwin.ingest.xes_loader import load_event_table

        return load_event_table(self.path, agent_col=self.agent_col)


class CsvEventsAdapter(EventSource):
    """CSV с колонками case_id, activity, timestamp, agent[, context]."""

    def __init__(self, path: str | Path, mapping: Optional[dict[str, str]] = None):
        self.path = Path(path)
        self.mapping = mapping or {
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "timestamp": "time:timestamp",
            "agent": "org:resource",
        }

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        out = df.rename(columns={k: v for k, v in self.mapping.items() if k in df.columns})
        for col in REQUIRED:
            if col not in out.columns:
                raise ValueError(f"CSV: нет колонки {col} после маппинга")
        out["time:timestamp"] = pd.to_datetime(out["time:timestamp"], utc=True, format="mixed")
        if "org:resource" not in out.columns:
            out["org:resource"] = out.get("agent", "UNKNOWN")
        return out


class SqlEventSource(EventSource):
    """
    Контракт будущего SQL-источника.

    Ожидаемый SELECT: case_id, activity, ts, agent [, context_value]
    → после маппинга: case:concept:name, concept:name, time:timestamp, org:resource[, context].

    Параметры:
      dsn   — строка подключения (не коммитить секреты)
      query — SELECT с окном по :fit_start / :fit_end (или без)
    """

    def __init__(self, dsn: str, query: str, mapping: Optional[dict[str, str]] = None):
        self.dsn = dsn
        self.query = query
        self.mapping = mapping or {
            "case_id": "case:concept:name",
            "activity": "concept:name",
            "ts": "time:timestamp",
            "agent": "org:resource",
        }

    def load(self) -> pd.DataFrame:
        raise NotImplementedError(
            "SQL-источник: задайте DSN и SELECT с колонками "
            "case_id, activity, ts, agent[, context]. Живой коннектор — вне v1 UI."
        )

    def pull(
        self,
        fit_start: Any | None = None,
        fit_end: Any | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "SQL pull(fit_start, fit_end): передайте окно в параметризованный SELECT. "
            "Живой коннектор — вне v1."
        )

    def dry_run(self) -> dict[str, Any]:
        return {
            "adapter": "sql",
            "expected_columns": list(self.mapping.keys()),
            "target_schema": list(REQUIRED) + ["org:resource"],
            "mapping": dict(self.mapping),
            "notes": "Параметры :fit_start / :fit_end опциональны для оконной выгрузки.",
        }


# устаревший алиас
SqlAdapterStub = SqlEventSource


class Bitrix24Adapter(EventSource):
    """
    Каркас коннектора Битрикс24 (CRM / задачи / смарт-процессы).

    config: {
      "webhook_url" | "portal" + "access_token",
      "entity": "crm.deal" | "tasks" | "spa",
      "mapping": {...}
    }
    """

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config or {})

    def load(self) -> pd.DataFrame:
        raise NotImplementedError(
            "Битрикс24: нужны учётные данные (входящий webhook или OAuth-токен портала). "
            "Живой коннектор — вне v1; см. docs/INGEST_CONNECTORS.md."
        )

    def dry_run(self) -> dict[str, Any]:
        entity = self.config.get("entity", "crm.deal")
        return {
            "adapter": "bitrix24",
            "entity": entity,
            "expected_schema": {
                "case_id": "ID сделки / задачи / элемента SPA",
                "activity": "стадия / статус / тип активности таймлайна",
                "timestamp": "DATE_CREATE / UPDATED / UF_* даты события",
                "agent": "ASSIGNED_BY_ID / RESPONSIBLE_ID / UF_USER",
                "context": "OPPORTUNITY / UF_* сумма / приоритет (опционально)",
            },
            "required_config_keys": ["webhook_url или (portal + access_token)", "entity"],
            "mapping": self.config.get("mapping") or {
                "ID": "case:concept:name",
                "STAGE_ID": "concept:name",
                "DATE_MODIFY": "time:timestamp",
                "ASSIGNED_BY_ID": "org:resource",
            },
        }


class OneCAdapter(EventSource):
    """
    Каркас коннектора 1С (документы / бизнес-процессы / регистры).

    config: {
      "odata_url" | "http_service",
      "user", "password" | "token",
      "document": "Документ.ЗаказКлиента" | ...,
      "mapping": {...}
    }
    """

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config or {})

    def load(self) -> pd.DataFrame:
        raise NotImplementedError(
            "1С: нужны учётные данные (OData / HTTP-сервис: URL, пользователь, пароль или токен). "
            "Живой коннектор — вне v1; см. docs/INGEST_CONNECTORS.md."
        )

    def dry_run(self) -> dict[str, Any]:
        return {
            "adapter": "1c",
            "document": self.config.get("document", "Документ.*"),
            "expected_schema": {
                "case_id": "Ссылка / Номер документа / бизнес-процесса",
                "activity": "Состояние / точка маршрута / вид операции",
                "timestamp": "Дата / ДатаИзменения / период регистра",
                "agent": "Ответственный / Автор / Исполнитель",
                "context": "СуммаДокумента / Организация (опционально)",
            },
            "required_config_keys": [
                "odata_url или http_service",
                "user+password или token",
                "document",
            ],
            "mapping": self.config.get("mapping") or {
                "Ref_Key": "case:concept:name",
                "Status": "concept:name",
                "Date": "time:timestamp",
                "Responsible_Key": "org:resource",
            },
        }


class SapAdapter(EventSource):
    """
    Каркас коннектора SAP (ECC / S/4HANA — заявки, заказы, workflow).

    config: {
      "odata_url" | "rfc_dest",
      "client", "user", "password" | "oauth",
      "object": "BUS2012" | "purchase_order" | ...,
      "mapping": {...}
    }
    """

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config or {})

    def load(self) -> pd.DataFrame:
        raise NotImplementedError(
            "SAP: нужны учётные данные (OData / RFC: client, user, password или OAuth). "
            "Живой коннектор — вне v1; см. docs/INGEST_CONNECTORS.md."
        )

    def dry_run(self) -> dict[str, Any]:
        return {
            "adapter": "sap",
            "object": self.config.get("object", "purchase_order"),
            "expected_schema": {
                "case_id": "EBELN / Object ID / Work item ID",
                "activity": "status / activity type / WI_STAT",
                "timestamp": "change timestamp / WI_CD+WI_CT",
                "agent": "uname / agent / responsible",
                "context": "NETWR / amount (опционально)",
            },
            "required_config_keys": [
                "odata_url или rfc_dest",
                "client",
                "user+password или oauth",
                "object",
            ],
            "mapping": self.config.get("mapping") or {
                "EBELN": "case:concept:name",
                "STATUS": "concept:name",
                "CHANGED_AT": "time:timestamp",
                "UNAME": "org:resource",
            },
        }


def normalize_event_table(df: pd.DataFrame, agent_col: str = "org:resource") -> pd.DataFrame:
    out = df.copy()
    for col in REQUIRED:
        if col not in out.columns:
            raise ValueError(f"Нет обязательной колонки {col}")
    if agent_col not in out.columns:
        out[agent_col] = "UNKNOWN"
    out[agent_col] = out[agent_col].fillna("UNKNOWN").astype(str)
    if "org:resource" not in out.columns:
        out["org:resource"] = out[agent_col]
    out["time:timestamp"] = pd.to_datetime(out["time:timestamp"], utc=True, format="ISO8601")
    return out.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)


__all__ = [
    "REQUIRED",
    "EventSource",
    "EventSourceAdapter",
    "XesAdapter",
    "CsvEventsAdapter",
    "SqlEventSource",
    "SqlAdapterStub",
    "Bitrix24Adapter",
    "OneCAdapter",
    "SapAdapter",
    "normalize_event_table",
]
