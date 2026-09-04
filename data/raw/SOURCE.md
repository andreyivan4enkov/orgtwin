# Донор v0 (один организм, без склейки)

- **Датасет:** BPI Challenge 2012  
- **DOI:** https://doi.org/10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f  
- **Организация:** один нидерландский финансовый институт (кредитный процесс)  
- **Окно времени:** 2011-10-01 → 2012-03-14  
- **Файлы:** `BPI_Challenge_2012.xes.gz` (MD5 `74c7ba9aba85bfcb181a22c9d565e5b5`), `DATA.xml`  
- **Почему этот донор:** индивидуальные `org:resource` → 1 сотрудник ≈ 1 нейроавтомат; единый процесс без франкенштейна из других корпусов.

Другие датасеты **не смешиваются** с этим прогоном.

---

# Донор v0.9.0 — BPIC2019 (закупки, не склеивать)

- **Датасет:** BPI Challenge 2019  
- **DOI:** https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1  
- **Организация:** закупки (coatings/paints), NL; ~628 `org:resource`  
- **Окно (после фильтра):** 2018-01-01 → 2020-04-09  
- **Файл:** `BPI_Challenge_2019.xes` (MD5 `4eb909242351193a61e1c15b9c3cc814`)  
- **Скрипт:** `scripts/download_bpic2019.py`  
- **Amount:** `Cumulative net worth (EUR)`; lifecycle отсутствует  

---

# Донор v0.8.0 (отдельный организм, не склеивать с BPIC2012)

- **Датасет:** Real-life event logs — Hospital log (BPIC 2011)
- **DOI:** https://doi.org/10.4121/uuid:d9769f3d-0ab0-4fb8-803b-0d1120ffcf54
- **Организация:** один нидерландский academic hospital, гинекология
- **Окно времени:** 2005-01-03 → 2008-03-20
- **Файлы:** `Hospital_log.xes.gz` (MD5 `482adef27906fb3f0b66989798edd987`)
- **Агент в прогоне:** `org:group` (отделение / лаборатория). Поля `org:resource` в логе нет.
- **Скрипт:** `scripts/download_hospital2011.py`

---

# Донор v0.8.1 — Sepsis Cases (медицина, не склеивать)

- **Датасет:** Sepsis Cases - Event Log
- **DOI:** https://doi.org/10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460
- **Организация:** NL hospital ERP (сепсис, ~1050 кейсов)
- **Окно:** 2013-11-07 → 2015-06-05 (~19 мес); 16 активностей
- **Файлы:** `Sepsis_Cases_Event_Log.xes.gz` (MD5 `b5671166ac71eb20680d3c74616c43d2`)
- **Агент:** `org:group`; контекст `Age`
- **Скрипт:** `scripts/download_sepsis.py`
