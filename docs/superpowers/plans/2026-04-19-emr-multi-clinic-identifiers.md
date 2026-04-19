# EMR Multi-Clinic Identifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `patients` 与 `providers` 同时支持 clinic 维度外部标识字段，兼容多 EMR（iClinic/eClinic/custom）与自定义 EMR 接入。

**Architecture:** 采用“最小侵入”策略：先扩展数据库列与 ORM，再扩展 API 输入输出和 service 过滤能力。所有新增字段默认可空，保证历史调用无破坏。测试以 schema/service 单元测试为主，避免依赖本地 Postgres。

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Pytest

---

### Task 1: 数据模型与迁移

**Files:**
- Create: `alembic/versions/014_patient_provider_clinic_identifiers.py`
- Modify: `app/models/patients.py`
- Modify: `app/models/providers.py`

- [ ] **Step 1: 写迁移文件（upgrade/downgrade）**
- [ ] **Step 2: 在 `Patient` 增加 `created_by/clinic_patient_id/clinic_id/division_id/clinic_system/clinic_name`**
- [ ] **Step 3: 在 `Provider` 增加 `provider_clinic_id/division_id/clinic_system/clinic_name`**
- [ ] **Step 4: 运行静态检查，确认模型可导入**
Run: `uv run python -c "import app.models; print('ok')"`
Expected: 输出 `ok`
- [ ] **Step 5: 自检迁移与模型字段命名一致**

### Task 2: Patients API 与 Service 扩展

**Files:**
- Modify: `app/services/patient_service.py`
- Modify: `app/api/v1/endpoints/patients.py`
- Create: `tests/services/test_patient_service_clinic_filters.py`

- [ ] **Step 1: 为 `PatientService.create/update` 接入新增字段赋值**
- [ ] **Step 2: 为 `PatientService.search` 增加过滤参数**
  - `clinic_patient_id`
  - `clinic_id`
  - `division_id`
  - `clinic_system`
- [ ] **Step 3: `patients.py` 的 `PatientCreate/PatientUpdate/PatientOut` 增加新字段**
- [ ] **Step 4: `search_patients` endpoint 增加对应 query 参数并透传给 service**
- [ ] **Step 5: 为 service 搜索条件新增测试（mock/stub SQL 条件）**
- [ ] **Step 6: 运行新增测试**
Run: `uv run pytest tests/services/test_patient_service_clinic_filters.py -q`
Expected: PASS

### Task 3: Providers API 与 Service 扩展

**Files:**
- Modify: `app/services/provider_service.py`
- Modify: `app/api/v1/endpoints/providers.py`
- Create: `tests/api/test_providers_clinic_fields.py`

- [ ] **Step 1: 在 Provider create/update 中支持 `provider_clinic_id/division_id/clinic_system/clinic_name`**
- [ ] **Step 2: 在 ProviderCreate/ProviderUpdate/ProviderOut 中暴露同字段**
- [ ] **Step 3: 补充 endpoint 级测试（mock `ProviderService`）**
- [ ] **Step 4: 运行新增 provider 测试**
Run: `uv run pytest tests/api/test_providers_clinic_fields.py -q`
Expected: PASS

### Task 4: 全量验证与回归检查

**Files:**
- Modify (if needed): `docs/superpowers/specs/2026-04-19-emr-multi-clinic-identifiers-design.md`

- [ ] **Step 1: 运行本次相关测试集合**
Run: `uv run pytest tests/services/test_patient_service_clinic_filters.py tests/api/test_providers_clinic_fields.py -q`
Expected: PASS
- [ ] **Step 2: 运行类型/风格检查**
Run: `uv run pytest tests/test_health.py -q`（若本地无 Postgres，记录已知失败原因）
- [ ] **Step 3: 执行代码评审（spec compliance -> code quality）并修复问题**
- [ ] **Step 4: 输出变更摘要与后续迁移注意事项**

