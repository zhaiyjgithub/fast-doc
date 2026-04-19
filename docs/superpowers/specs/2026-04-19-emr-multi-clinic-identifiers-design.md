# EMR Multi-Clinic Identifier Support Design

**Problem**
`patients` 和 `providers` 目前只有通用身份字段（如 `mrn`、`external_provider_id`），无法稳定承载跨 EMR（`iClinic`、`eClinic`、自定义）场景下的组织/分院/实体映射。

**Design Goal**
为患者与医生增加 clinic 维度的外部标识，支持多 EMR / 自定义 EMR 的统一接入与检索，不破坏现有接口兼容性。

## Scope

### In Scope
- 数据库新增字段（`patients`、`providers`）
- SQLAlchemy model 同步
- patients/providers API schema（create/update/out）同步
- `PatientService.search` 增加 clinic 相关过滤
- 新增测试（以无外部依赖为主）

### Out of Scope
- 历史数据回填脚本
- EMR 接入流程改造（本次只做数据模型与 API 扩展）
- 强制唯一约束策略（先允许宽松写入，后续根据真实数据收敛）

## Data Model

### `patients` 新增字段
- `created_by: UUID | NULL`  
  创建该患者记录的用户 ID（关联 `users.id`，可空）。
- `clinic_patient_id: String(128) | NULL`  
  外部 EMR 内的患者 ID（clinic 范围）。
- `clinic_id: String(128) | NULL`  
  外部 clinic/机构 ID。
- `division_id: String(128) | NULL`  
  外部分院/科室/业务单元 ID。
- `clinic_system: String(32) | NULL`  
  值域建议：`iClinic` / `eClinic` / `custom`（当前阶段用字符串，后续可演进 enum）。
- `clinic_name: String(128) | NULL`  
  机构展示名。

### `providers` 新增字段
- `provider_clinic_id: String(128) | NULL`  
  外部 clinic 范围内医生 ID。
- `division_id: String(128) | NULL`  
  外部分院/科室/业务单元 ID。
- `clinic_system: String(32) | NULL`  
  值域建议：`iClinic` / `eClinic` / `custom`（当前阶段用字符串，后续可演进 enum）。
- `clinic_name: String(128) | NULL`  
  医生所属机构展示名。

## API Contract Changes

### Patients
- `POST /v1/patients` 支持写入新增字段
- `PUT /v1/patients/{id}` 支持更新新增字段
- `GET /v1/patients` 与 `GET /v1/patients/{id}` 返回新增字段
- `GET /v1/patients/search` 支持过滤参数：
  - `clinic_patient_id`
  - `clinic_id`
  - `division_id`
  - `clinic_system`

### Providers
- `POST /v1/providers` 支持写入：
  - `provider_clinic_id`
  - `division_id`
  - `clinic_system`
  - `clinic_name`
- `PUT /v1/providers/{id}` 支持更新同上字段
- `GET /v1/providers` / `GET /v1/providers/{id}` 返回同上字段

## Migration Plan

- 新增 Alembic migration（head 之后）
- `upgrade`：向 `patients`/`providers` `add_column`
- `downgrade`：对应 `drop_column`
- 不做 destructive 变更，不改现有字段语义

## Validation & Error Handling

- 新字段全部可空，确保兼容旧客户端
- API 不强制枚举校验 `clinic_system`（避免阻塞未知 EMR）；先约定推荐值

## Testing Strategy

- 新增 service 层单测（`PatientService.search` 的 clinic 过滤 SQL 组合）
- 新增 providers/patients endpoint schema round-trip 测试（mock service）
- 由于本地缺少 Postgres，本轮验证以：
  - 静态类型检查（`uv run pytest` 中不触发 DB 的测试）
  - API schema 序列化逻辑
  - 变更文件 lint/compile

## Risks

- `clinic_system` 目前为自由文本，可能产生脏值；后续可加白名单与归一化层。
- 无唯一约束会允许重复映射；但可避免早期接入受限，后续根据数据分布再收敛。

## Rollout

1. 先发 migration + API 字段（向后兼容）
2. EMR 接入方逐步写入新增字段
3. 观察数据质量后决定是否添加组合索引/唯一约束

