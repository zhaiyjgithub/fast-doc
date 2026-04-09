# AI EMR Backend Plan v2.2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Changelog from v2.1**:
> - Task 0: Added all `app/models/` file creation, `pyproject.toml` dependency lock, Docker Compose pgvector verification, embedding dimension pre-check.
> - Task 1: Added `encryption_service.py` for SSN/PHI field encryption.
> - Task ordering: RAG ingestion (was Task 4.5) promoted to Task 3 so PatientRAG and GuidelineRAG have data for integration tests.
> - Tasks renumbered: 3→4, 4→5, 5→6, 6→7, 7→8, 8→9.
> - Task 7: Added ICD/CPT data source policy and catalog version tracking.
>
> **Changelog from v2.3**:
> - Task 7: Full architectural decision — ICD/CPT uses structured catalog (SQL) for MVP, NOT RAG. Added `keyword_extractor.py` (SQL pre-filter for prompt injection), complete `catalog_ingestion_service` spec with CMS download URL, CPT fixture strategy, and detailed rule engine checks. v2 path for coding_reference RAG documented.
> - Acceptance criteria: Added embedding dimension freeze gate, clarified P95 latency baseline conditions.
> - Risk controls: Added encryption key management and audit immutability policies.
>
> **Changelog from v2.2**:
> - Added "Recommended Execution Order" section with full phase breakdown.
> - Added "Test Data Strategy" section: CSV fixture audit, respiratory data gap analysis, guideline PDF sources.
> - Task 3: Added CSV seed step and fixture file reference.
> - Task 4/5: Updated integration test strategy to use seeded fixtures.
>
> **Changelog from v2.10 (this version)**:
> - **Schema: `providers` 表字段扩充**：新增 `first_name`, `last_name`, `gender`, `date_of_birth`, `credentials`（MD/DO/NP/PA）, `sub_specialty`, `license_number`, `license_state`, `prompt_style`, `updated_at`。`full_name` 保留作展示字段。`date_of_birth`/`license_number` 存储但不注入 LLM prompt（PHI 最小化）。
> - **Task 6 新增 Provider-aware Prompt 设计**：`emr_service.py` 在构建 EMR system prompt 时，通过 `encounter.provider_id` 加载 provider，按 `specialty`、`sub_specialty`、`prompt_style` 三个维度定制 prompt。定义 `SPECIALTY_PROMPT_PREFIXES`、`SUB_SPECIALTY_ADDITIONS`、`PROMPT_STYLE_INSTRUCTIONS` 映射表。`provider_id=NULL` 时优雅 fallback 到 standard 模式。新增 Task 6 Step 4 的 provider-aware prompt 测试规格（4 个测试场景）。
> - **`EMRGraphState` 补充字段**：新增 `provider_id`、`provider_specialty`、`provider_prompt_style` 三个字段，在图入口处从 encounter 预加载（避免各 node 重复查库）。
> - **`providers.csv` fixture 更新**：补充 `first_name`, `last_name`, `gender`, `date_of_birth`, `credentials`, `sub_specialty`, `license_number`, `license_state`, `prompt_style` 字段；d002（Dr. James Park）设为 `sub_specialty=critical_care`, `prompt_style=detailed`。
> - **Schema migration `001_init`**：补充 `providers` 表完整字段说明。
>
> **Changelog from v2.9 (this version)**:
> - **全计划路径修复**：`fast-doc/` 根目录引用统一改为 `fast-doc/docs/medical-codes/`、`fast-doc/docs/guidelines/`、`fast-doc/docs/fixtures/`（文件已在上一步移动）。影响 Gate 3、Scope Lock、Task 3.1 PDF 表、Task 7 数据文件引用、`ingest_icd()`/`ingest_cpt()` 路径。
> - **Task 0 新增**：`.env.example` 加入 Files to create 列表；Step 4 拆分为 Step 4（创建 `.env.example`）+ Step 5（实现 `config.py`），后续步骤顺序相应调整。`config.py` 明确包含 MinerU config keys。
> - **Task 0 依赖新增**：`pyproject.toml` 补充 `aiofiles>=23.0.0`（异步文件读取）和 `python-multipart>=0.0.9`（FastAPI multipart 支持 `POST /v1/rag/markdown`）。
> - **Task 3 预检清单更新**：标记所有 CSV fixture 和 5 个 PDF 均已准备就绪（✅），更新为从 `fast-doc/docs/` 路径复制到项目 `fixtures/` 目录，移除重复下载指令。
> - **Task 3 `seed_fixtures.py` 修复**：改为直接调用 `MarkdownIngestionService.ingest_markdown()`（而非通过 HTTP 调用自身 API），消除服务未启动时 seed 失败的风险。
> - **Task 3.1 `_poll_batch()` 修复**：补充 `waiting-file` 状态说明（MinerU 尚未检测到 PUT 上传时的过渡态），明确各状态转换顺序（waiting-file → pending → running → done|failed）。
> - **Task 7 新增 `scripts/ingest_catalogs.py`**：明确了 ICD/CPT catalog 数据入库的触发方式，包含 CLI 用法和完整的四步 DB 初始化顺序（alembic → seed → ingest_guidelines → ingest_catalogs）。
>
> **Changelog from v2.8 (this version)**:
> - **Task 3 (新增)**: `MarkdownIngestionService` 设计为三层 ingestion 架构的 Layer 1（共享核心管道）：
>   - 新服务 `app/services/markdown_ingestion_service.py`：统一处理 markdown → chunk → embed → persist。
>   - 自动检测 `![image](url)` 并按 `enrich_images` 开关路由 `ImageEnricher`。
>   - `reingest=True` 按 `document_id` 删除旧 chunk，`metadata_extra` 注入每个 chunk 的 `metadata_json`。
>   - 新 API 端点 `POST /v1/rag/markdown`：支持 JSON body（markdown 字符串）和 multipart 文件上传（`.md` 文件），适用于 guideline 和 patient namespace。
>   - 响应新增 `images_described`, `skipped_images` 字段。
>   - 补充 `tests/api/test_rag_markdown.py` 和 `tests/services/test_markdown_ingestion_service.py`。
> - **Task 3.1 (更新)**: `GuidelineIngestionService.ingest_pdf()` 简化为 2 步（MinerU → `MarkdownIngestionService`），不再内部管理 chunking/dedup/embed/persist。
>   - `scripts/ingest_guidelines.py` 新增 `--markdown-dir` 选项：跳过 MinerU，直接从预转换的 `.md` 文件导入（仍运行 ImageEnricher）。
>   - Task 3.1 file list 更新，移除 `serve_local_files.py`（Token API 直传已无需本地 HTTP server）。
>
> **Changelog from v2.7 (this version)**:
> - Task 3.1: 全面切换到 MinerU **Token-based 精准解析 API**（`/api/v4/`，支持 ≤200MB/≤600页）：
>   - 本地文件上传走 `/api/v4/file-urls/batch` → PUT 直传（不再需要 tmpfiles.org）
>   - 远程 URL 走 `/api/v4/extract/task`
>   - 结果为 `full_zip_url` ZIP 包，提取 `full.md`（新增 `_download_markdown_from_zip()`）
>   - 推荐 `model_version=vlm`，`language=en`，`is_ocr=true`
>   - config 重构：`MINERU_MODEL_VERSION`, `MINERU_LANGUAGE`, `MINERU_MAX_WAIT=900`；移除 `PUBLIC_FILE_URL`
> - Guideline manifest 扩展到全部 5 个 PDF（GINA Strategy Report 11MB + GOLD Report 16MB 升为 P0）
> - 验收标准更新：5 `KnowledgeDocument`，≥500 chunks
>
> **Changelog from v2.6 (this version)**:
> - Task 1: `llm_adapter` 新增 `describe_image(image_url, context_hint)` 方法，调用 `QWEN_VL_MODEL`（qwen-vl-max）生成图片文字描述；新增 `QWEN_VL_MODEL` config key。
> - Task 3.1: 管道新增 `[2] ImageEnricher` 步骤（MinerU → **ImageEnricher** → DocumentChunker → embed → persist）。ImageEnricher 分类图片（装饰性 vs 临床），装饰图移除，临床图调用 Qwen-VL 生成描述并替换原位置。新增 `image_enricher.py` 和 `test_image_enricher.py`。`GuidelineIngestionService.ingest_pdf()` 更新为 6 步管道，`reingest=True` 按 `document_id` 删除（修复 title 匹配的 bug）。`metadata_json` 新增 `has_image_description` 字段。`IMAGE_DESCRIPTION_ENABLED` config 开关用于测试提速。
>
> **Changelog from v2.5 (this version)**:
> - 全计划 review 修复 9 处问题：
>   - Task 3 Step 6: 移除 pypdf，改为调用 Task 3.1 的 `scripts/ingest_guidelines.py`
>   - Task 3 Step 6: seed 脚本明确写入 `abnormal_flag` 到 chunk `metadata_json`
>   - Task 3 Step 3: 统一 chunk size 标准为 `DocumentChunker`（1000 chars/200 overlap），删除 512-token 描述
>   - Task 3 guideline chunk 验收数量改为 >= 200（与 Task 3.1 一致）
>   - Schema：`cpt_catalog` 补 `short_name`, `description`, `avg_fee`, `rvu` 字段，并写明 CSV 字段映射
>   - Task 5 GuidelineRAG：keyword 查询改为参数化（消除 SQL 注入风险），补充 keyword_match_score 计算方式和无结果 fallback
>   - Task 0：补充 `tests/conftest.py` 规格（test DB session、事务回滚隔离、async_client fixture、asyncio_mode）；`alembic/env.py` 通过 `Settings` 读取 `DATABASE_URL`
>   - Gate 3：标记 CPT 数据已到位
>   - Task 7 Step 3：验收数量改为 ~354 行
>
> **Changelog from v2.4**:
> - Task 7: CPT 数据已到位（`Ref_CPT_202604091710.csv`，23,089 条全量 CPT，含 AvgFee/RVU）。更新 `ingest_cpt()` spec 为 CSV 清洗逻辑（strip 空格、过滤 deleted 3,801 条 + 非标准本地扩展码 5 条、空 CPTDesc fallback、fee/RVU 转 float）；`catalog_version` 改为 `CPT-2026-04`；全量加载，不限章节。Risk Control 改为数据质量风险说明。
>
> **Changelog from v2.3 (this version)**:
> - CSV fixtures updated: all 8 files now contain respiratory-scope data (Asthma/COPD/CAP), `primary_language=en-US`, added `encounter_context` column, added `providers.csv`.
> - GINA & GOLD PDFs confirmed downloaded to `fast-doc/` root (5 files, 43 MB total).
> - Added Task 3.1: MinerU Service + Guideline PDF Extraction & RAG Ingestion — MinerU API replaces pypdf for accurate table/multi-column extraction; MinerUService designed as shared infrastructure for future patient document OCR.
> - `pyproject.toml` deps: removed `pypdf`/`ftfy`; MinerU is API-only (no local lib needed).

**Goal:** Build a backend-only AI EMR MVP using Qwen APIs + LangGraph + DualRAG (`patient_rag` and `guideline_rag`) to generate EMR and ICD/CPT suggestions with auditable evidence and human review safeguards.

**Architecture:** FastAPI service with LangGraph orchestration. Two parallel retrieval routes (patient and guideline) feed context merge, then EMR generation and coding nodes run with deterministic rule checks. Persist request-level traces for auditability.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, asyncpg, Alembic, PostgreSQL 17 + pgvector, LangGraph, langchain-openai (Qwen compatible), cryptography, httpx, pytest, pytest-asyncio, Docker Compose.

**Schema reference:** See `patient_data_schema_design_5bb4a05d.plan.md` for full table definitions, field specs, and migration sequence.

---

## Scope

- Input: `patient_id`, `transcript_text`, optional `encounter_context`.
- Output:
  - `emr_json` (`subjective/objective/assessment/plan`)
  - `emr_text`
  - `icd_suggestions` (top_n/confidence/rationale/evidence)
  - `cpt_suggestions` (top_n/confidence/modifier_hint/evidence)
- Hard constraints:
  - Use Qwen API for chat + embeddings.
  - Use LangGraph for orchestration.
  - DualRAG fixed as:
    - Route-1: `patient_rag`
    - Route-2: `guideline_rag`
- Target deployment:
  - US private clinics as primary user environment.
  - Intake and demographics fields follow US front-desk workflows.
- Compliance baseline:
  - Suggestions default to `needs_review`.
  - Persist model and evidence traces.
  - PHI handling aligned with HIPAA minimum-necessary principle.
  - Full SSN stored encrypted only; `ssn_last4` for display/search.

## Scope Lock (MVP)

- Market and deployment: US private clinics only.
- Specialty focus: respiratory clinic workflows first.
- Language policy: English-only (`en-US`) for input normalization, EMR output, coding prompts, and retrieval prompts.
- Guideline policy: ingest and retrieve respiratory English guideline documents only in MVP.
- ICD catalog: ICD-10-CM 2025, respiratory chapter (J00–J99) only.
- CPT catalog: ✅ 数据已到位（`fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv`，23,089 条全量 CPT）；ingestion 时执行数据清洗（strip 空格、过滤 deleted/非标准码），全量加载到 `cpt_catalog`，`catalog_version = "CPT-2026-04"`。
- Guideline PDF ingestion: MVP ingests all 5 PDFs via MinerU Token API (精准解析，支持 ≤200MB)：GINA Summary 2025, GINA Severe Asthma 2025, GINA Strategy Report 2025, GOLD Pocket Guide 2025, GOLD Report 2025。已下载至 `fast-doc/docs/guidelines/`。无文件大小限制瓶颈。
- Explicitly out-of-scope for MVP: multilingual outputs, cross-specialty expansion, non-US localization, CPT full catalog, partition-by-time for ops tables, patient-side document upload API (paper EMR / lab image OCR via MinerU is v2; MinerUService + ImageEnricher built in Task 3.1 as shared infrastructure, patient upload endpoint deferred).

---

## Recommended Execution Order

RAG 层必须先于 AI 诊断层完成，原因是 EMR 生成依赖两路检索结果作为上下文输入。PatientRAG 和 GuidelineRAG 的 retrieval service 又依赖 ingestion pipeline 预先写入数据，因此 ingestion 必须排在 retrieval 之前。

```
Phase 1 — 基础层（无相互依赖，可并行）
  Task 0  Project & DB Bootstrap
  Task 1  Qwen Integration + Security Baseline
  Task 2  LangGraph Workflow Skeleton（全 stub）

Phase 2 — RAG 层（顺序依赖）
  Task 3  RAG Ingestion Endpoint
  ↓ [载入测试数据：seed CSV fixtures + 下载指南 PDF]
  Task 4  PatientRAG Retrieval
  Task 5  GuidelineRAG Retrieval

Phase 3 — AI 诊断层（依赖 Phase 2 完成）
  Task 6  Context Merge + EMR Generation
  Task 7  ICD/CPT Catalog + Coding

Phase 4 — 合规与收尾
  Task 8  Auditability & Observability
  Task 9  Report API + Acceptance Gates
```

> **关键约束**：Task 3 必须在 Task 4/5 之前完成，否则 PatientRAG 和 GuidelineRAG 的集成测试无数据可检索。LangGraph skeleton（Task 2）可在 Task 1 完成后立即并行进行，因为其节点全为 stub，不依赖任何 RAG 或 DB 数据。

---

## Test Data Strategy

### 现有 CSV Fixtures 审计

目录 `fast-doc/` 下已有以下 CSV 文件，作为虚构患者数据来源：

| 文件 | 行数（含 header） | 当前状态 |
|------|-----------------|---------|
| `patients.csv` | 3+ 行 | ⚠️ 语言字段为 `zh`，违反 MVP 英文限定 |
| `patient_demographics.csv` | 3+ 行 | ✅ US 字段完整（地址/SSN/电话） |
| `encounters.csv` | 3+ 行 | ⚠️ 科室为 endocrinology/cardiology，非呼吸科 |
| `lab_reports.csv` | 4 行 | ⚠️ 报告内容为血糖/血脂/WBC，非呼吸科指标 |
| `lab_results.csv` | 3+ 行 | ⚠️ 指标为 FBG/HbA1c，非呼吸科 |
| `medication_records.csv` | 3+ 行 | ⚠️ 药物为 Metformin/Amlodipine，非呼吸科 |
| `allergy_records.csv` | 3+ 行 | ✅ 通用过敏（青霉素/海鲜），可保留 |
| `diagnosis_records.csv` | 3+ 行 | ⚠️ 诊断为糖尿病/高血压，非呼吸科 |

**缺失文件：**
- `providers.csv`：encounters 引用 `provider_id`（d001/d002）但无对应表

### 修复要求（在 Task 3 seed 步骤执行前完成）

MVP scope 为**呼吸科**，需补充或替换以下数据：

**1. `patients.csv`**：将 `primary_language` 从 `zh` 改为 `en-US`。至少保留 3 位虚构患者：
  - Patient A: 哮喘（Asthma）
  - Patient B: COPD
  - Patient C: 社区获得性肺炎（CAP）

**2. `encounters.csv`**：将 `department` 改为 `pulmonology`；transcript 改为呼吸科场景（喘息/咳嗽/呼吸困难等主诉）；增加 `encounter_context` 列（JSONB 格式字符串，可为空 `{}`）。

**3. `lab_results.csv` + `lab_reports.csv`**：替换为呼吸科相关指标，例如：
  - 肺功能：FEV1, FEV1/FVC ratio（哮喘/COPD 必测）
  - 血氧：SpO2
  - 炎症：WBC, CRP, Procalcitonin（肺炎鉴别）
  - 痰培养结果（CAP 患者）

**4. `medication_records.csv`**：替换为呼吸科常用药，例如：
  - 沙丁胺醇（Salbutamol/Albuterol）— 哮喘急性期
  - 布地奈德（Budesonide）— ICS 控制药
  - 噻托溴铵（Tiotropium）— COPD 维持
  - 阿莫西林克拉维酸（Amoxicillin-Clavulanate）— CAP 一线

**5. `diagnosis_records.csv`**：替换 ICD-10-CM 呼吸科诊断：
  - J45.40 — Moderate persistent asthma, uncomplicated
  - J44.1 — COPD with acute exacerbation
  - J18.9 — Pneumonia, unspecified organism

**6. 新建 `providers.csv`**（最小字段）：
```csv
provider_id,external_provider_id,full_name,specialty,department,is_active
d001,NPI-001,Dr. Sarah Chen,Pulmonology,pulmonology,true
d002,NPI-002,Dr. James Park,Pulmonology,pulmonology,true
```

### 指南 PDF 来源（GuidelineRAG 使用）

以下文件均为官方免费 PDF，可直接下载用于 MVP ingestion：

**GINA 哮喘指南（Global Initiative for Asthma）**

| 文档 | 版本 | 下载链接 |
|------|------|---------|
| GINA Strategy Report 2025（完整版） | 2025 | [ginasthma.org/wp-content/uploads/2025/05/GINA-Strategy-Report_2025-WEB-WMS.pdf](https://ginasthma.org/wp-content/uploads/2025/05/GINA-Strategy-Report_2025-WEB-WMS.pdf) |
| GINA Summary Guide 2025（精简版，推荐优先） | 2025 | [ginasthma.org/wp-content/uploads/2025/06/GINA-Summary-Guide-2025-WEB_FINAL-WMS.pdf](https://ginasthma.org/wp-content/uploads/2025/06/GINA-Summary-Guide-2025-WEB_FINAL-WMS.pdf) |

**GOLD COPD 指南（Global Initiative for Chronic Obstructive Lung Disease）**

| 文档 | 版本 | 下载链接 |
|------|------|---------|
| GOLD 2025 Report（完整版） | 2025 | [goldcopd.org/wp-content/uploads/2024/11/GOLD-2025-Report-v1.0-15Nov2024_WMV.pdf](https://goldcopd.org/wp-content/uploads/2024/11/GOLD-2025-Report-v1.0-15Nov2024_WMV.pdf) |
| GOLD 2025 Pocket Guide（快速参考，推荐优先） | 2025 | [goldcopd.org/wp-content/uploads/2024/12/Pocket-Guide-2025-v1.2-FINAL-covered-13Dec2024_WMV.pdf](https://goldcopd.org/wp-content/uploads/2024/12/Pocket-Guide-2025-v1.2-FINAL-covered-13Dec2024_WMV.pdf) |

> **MVP ingestion 建议**：优先使用 Summary Guide（GINA）和 Pocket Guide（GOLD），文档较小（约 20–40 页），chunk 后约 100–200 个向量，适合 MVP 规模。完整版报告可作为 v2 扩展。

> **版权说明**：两份指南均为 Creative Commons 或免费教育用途授权，允许非商业使用。文档带有官方水印，ingestion 时保留 `source_ref_id` 和 `version` 字段以满足溯源要求。

### Fixture 文件存放规范

所有测试 fixture 存放在项目目录：
```
fixtures/
├── csv/
│   ├── patients.csv
│   ├── patient_demographics.csv
│   ├── providers.csv
│   ├── encounters.csv
│   ├── lab_reports.csv
│   ├── lab_results.csv
│   ├── medication_records.csv
│   ├── allergy_records.csv
│   └── diagnosis_records.csv
└── guidelines/
    ├── GINA-Summary-Guide-2025.pdf
    └── GOLD-Pocket-Guide-2025.pdf
```

Task 3 的 seed 脚本（`scripts/seed_fixtures.py`）负责读取 CSV 文件、写入 DB，并调用 ingestion service 将患者记录和指南 PDF 转为 `knowledge_chunks`。

---

## Pre-Implementation Gates

Before starting Task 0, verify the following:

- [ ] **Gate 1 – Embedding dimension**: Make one live call to `POST /compatible/v1/embeddings` (Qwen `text-embedding-v3`) with a test string. Record the output vector length. **Lock this value in `app/core/config.py` as `EMBEDDING_DIM`.** Do not proceed to migration `001` until this is confirmed. Expected: `1024`.
- [ ] **Gate 2 – Docker + pgvector**: Confirm `docker/docker-compose.yml` uses `pgvector/pgvector:pg17` (not plain `postgres:17`). Run `docker compose up -d db` and verify `CREATE EXTENSION IF NOT EXISTS vector;` succeeds.
- [x] **Gate 3 – ICD data file**: ✅ Already downloaded and processed. Files in `fast-doc/docs/medical-codes/`:
  - `ICD10-CM-Code-Descriptions-2025.zip` — original zip from CDC/NCHS (2.3 MB)
  - `icd10cm-codes-2025.txt` — raw codes file, 23,082 billable codes (6.1 MB)
  - `icd10cm_full_2025.tsv` — cleaned TSV: `code, description, chapter, catalog_version` (all 23,082 codes)
  - `icd10cm_J_respiratory_2025.tsv` — **respiratory chapter only**: 354 J codes, ready for MVP ingestion
  - ✅ CPT 数据已到位：`fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv`（23,089 条，含 AvgFee/RVU）

---

## Execution Tasks (v2.2)

### Task 0: Project & DB Bootstrap

**Purpose:** Establish the complete project skeleton — dependencies, DB session, all ORM model files, and Alembic migrations — so every subsequent task only modifies existing files.

**Files to create:**
```
pyproject.toml                          ← update with all deps (see dep list below)
app/__init__.py
app/main.py
app/core/__init__.py
app/core/config.py                      ← settings + EMBEDDING_DIM constant
app/db/__init__.py
app/db/base.py                          ← declarative base
app/db/session.py                       ← async session factory
app/models/__init__.py
app/models/patients.py                  ← Patient, PatientDemographics
app/models/providers.py                 ← Provider
app/models/clinical.py                  ← Encounter, EmrNote, DiagnosisRecord,
                                           MedicationRecord, LabReport,
                                           LabResult, AllergyRecord
app/models/coding.py                    ← IcdCatalog, CptCatalog,
                                           CodingSuggestion, CodingEvidenceLink
app/models/rag.py                       ← KnowledgeDocument, KnowledgeChunk,
                                           RetrievalLog
app/models/ops.py                       ← LlmCall, AuditEvent
app/api/__init__.py
app/api/v1/__init__.py
app/api/v1/router.py
alembic.ini
alembic/env.py
alembic/versions/001_init.py            ← pgvector ext + patients + demographics + providers
alembic/versions/002_encounters.py
alembic/versions/003_longitudinal.py
alembic/versions/004_coding.py
alembic/versions/005_rag.py             ← knowledge_chunks uses VECTOR(EMBEDDING_DIM)
alembic/versions/006_ops.py
alembic/versions/007_indexes.py
tests/__init__.py
tests/conftest.py                       ← shared fixtures: test DB session, async client
tests/test_health.py
tests/db/__init__.py
tests/db/test_connection.py
.env.example                            ← developer onboarding template (no real secrets)
```

**Required `pyproject.toml` dependencies:**
```toml
[project]
name = "ai-emr"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pgvector>=0.3.0",
    "langgraph>=0.2.0",
    "langchain-core>=0.2.0",
    "langchain-openai>=0.1.0",
    "httpx>=0.27.0",
    "cryptography>=42.0.0",
    "aiofiles>=23.0.0",          # async file I/O for seed scripts and markdown upload
    "python-multipart>=0.0.9",   # FastAPI multipart/form-data for POST /v1/rag/markdown
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-httpx>=0.30.0",
]
```

**Steps:**
- [ ] Step 1: Update `pyproject.toml` with the full dependency list above. Run `uv sync` and confirm no conflicts.
- [ ] Step 2: Implement `tests/conftest.py` with shared pytest fixtures:
  - `test_db_url`: reads `TEST_DATABASE_URL` from env (separate DB from production, e.g. `postgresql+asyncpg://user:pass@localhost/emr_test`).
  - `async_session` fixture: creates async DB session per test, wraps each test in a transaction and rolls back on teardown (test isolation without truncation overhead).
  - `async_client` fixture: `httpx.AsyncClient` pointed at the FastAPI test app.
  - Add `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` with `asyncio_mode = "auto"`.
- [ ] Step 3: Write failing tests: `tests/test_health.py` (GET /health → 200) and `tests/db/test_connection.py` (async session connects, `SELECT 1` succeeds).
- [ ] Step 4: Create `.env.example` with all required env vars (no real values):
  ```
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/emr_dev
  TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/emr_test
  QWEN_API_KEY=sk-your-key-here
  QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
  QWEN_CHAT_MODEL=qwen-max
  QWEN_EMBEDDING_MODEL=text-embedding-v3
  QWEN_VL_MODEL=qwen-vl-max
  EMBEDDING_DIM=1024
  ENCRYPTION_KEY=base64-encoded-32-bytes-here
  MINERU_API_KEY=your-mineru-token-here
  IMAGE_DESCRIPTION_ENABLED=true
  ```
- [ ] Step 5: Implement `app/core/config.py` with `Settings` (Pydantic BaseSettings): `DATABASE_URL`, `TEST_DATABASE_URL`, `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_CHAT_MODEL`, `QWEN_EMBEDDING_MODEL`, `QWEN_VL_MODEL: str = "qwen-vl-max"`, `EMBEDDING_DIM: int = 1024`, `ENCRYPTION_KEY`, and all MinerU config keys from Task 3.1.
- [ ] Step 6: Implement `app/db/base.py` (declarative base) and `app/db/session.py` (async engine + session factory). Import `Settings` in `alembic/env.py` to get `DATABASE_URL` — this is how Alembic reads config at migration time.
- [ ] Step 7: Create all ORM model files listed above. Each file should define the model class(es) with columns matching the schema plan. Use `from app.db.base import Base`. Models should be importable but tables are created via Alembic, not `Base.metadata.create_all`.
- [ ] Step 8: Configure Alembic (`alembic.ini` + `alembic/env.py`). Write all 7 migration files in sequence. Migration `004` must include `cpt_catalog` with `short_name`, `description`, `avg_fee`, `rvu` columns. Migration `005` must use `EMBEDDING_DIM` from config for the `VECTOR(n)` column.
- [ ] Step 9: Run `alembic upgrade head` against the test DB. Confirm all tables and indexes are created.
- [ ] Step 10: Run tests. All health and connection tests must pass.
- [ ] Step 11: Commit.

---

### Task 1: Qwen Integration + Security Baseline

**Purpose:** Establish the only outbound HTTP client and the encryption service. No other task should make direct HTTP calls or implement encryption logic.

**Files to create/modify:**
```
app/services/__init__.py
app/services/qwen_client.py             ← sole outbound Qwen HTTP client
app/services/llm_adapter.py            ← strategy layer (chat + embed + describe_image)
app/services/encryption_service.py     ← AES-256-GCM for SSN/PHI fields
app/core/config.py                     ← add ENCRYPTION_KEY + QWEN_VL_MODEL validation
tests/services/test_qwen_client.py
tests/services/test_llm_adapter.py
tests/services/test_encryption_service.py
tests/services/test_log_redaction.py
```

**Steps:**
- [ ] Step 1: Write failing tests for `qwen_client`: chat success, embedding success, vision description success, HTTP 429 → `RateLimitError`, HTTP 5xx → `UpstreamError`.
- [ ] Step 2: Implement `qwen_client.py` using `httpx.AsyncClient`. Must use `QWEN_API_KEY` from config. No hardcoded URLs or keys anywhere. Log redaction must strip `Authorization` header before logging.
- [ ] Step 3: Implement `llm_adapter.py` as the strategy interface with three methods:
  - `chat(messages: list[dict]) → str` — text chat via `QWEN_CHAT_MODEL`
  - `embed(text: str) → list[float]` — text embedding via `QWEN_EMBEDDING_MODEL`
  - `describe_image(image_url: str, context_hint: str = "") → str` — vision description via `QWEN_VL_MODEL`

  `describe_image()` implementation:
  ```python
  async def describe_image(self, image_url: str, context_hint: str = "") -> str:
      """
      Call Qwen-VL to generate a text description of a clinical image.
      Uses OpenAI-compatible multimodal message format.
      context_hint: surrounding section heading for better-grounded description.
      """
      prompt = (
          f"This image appears in a clinical guideline document under the section: '{context_hint}'. "
          "Describe all clinical information visible in this image in detail: "
          "include all text, numerical values, decision logic, flowchart steps, "
          "table contents, scale descriptions, and any clinical recommendations. "
          "Output plain text only, no markdown."
      )
      messages = [
          {
              "role": "user",
              "content": [
                  {"type": "image_url", "image_url": {"url": image_url}},
                  {"type": "text", "text": prompt},
              ],
          }
      ]
      # POST to QWEN_BASE_URL/chat/completions with model=QWEN_VL_MODEL
      # Same auth header as chat; same error handling
  ```
- [ ] Step 4: Write failing tests for `encryption_service`: encrypt/decrypt round-trip, tampered ciphertext raises error, missing key raises startup error.
- [ ] Step 5: Implement `encryption_service.py` using `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Storage format: `base64(12-byte-nonce + ciphertext + 16-byte-tag)`. Load key from `ENCRYPTION_KEY` env var (base64-encoded 32 bytes). Raise `ValueError` at import time if key is absent or wrong length.
- [ ] Step 6: Write and run log redaction tests: assert that log output for requests containing `ssn`, `phone`, `address`, `Authorization` contains only redacted placeholders.
- [ ] Step 7: Run all tests.
- [ ] Step 8: Commit.

---

### Task 2: LangGraph Workflow Skeleton

**Purpose:** Define the complete graph topology and state schema. All nodes are stubs; real logic is filled in Tasks 4–8.

**Files to create:**
```
app/graph/__init__.py
app/graph/state.py                      ← EMRGraphState TypedDict
app/graph/nodes.py                      ← all node stubs
app/graph/workflow.py                   ← compiled graph
tests/graph/__init__.py
tests/graph/test_workflow_bootstrap.py
```

**Node list (all stubs in this task):**
```
patient_rag_node
guideline_rag_node
context_merge_node
emr_generation_node
icd_coding_node
cpt_coding_node
rule_check_node
persist_node
retry_node
fail_safe_node
```

**State fields (`EMRGraphState`):**
```python
patient_id: str
transcript_text: str
encounter_context: dict | None
encounter_id: str | None
request_id: str
provider_id: str | None         # loaded from encounter; used to build specialty-aware prompt
provider_specialty: str | None  # denormalized for prompt routing (avoids extra DB query in nodes)
provider_prompt_style: str      # "standard" | "detailed" | "concise" | "critical_care"
patient_chunks: list
guideline_chunks: list
merged_context: dict | None
conflict_flags: list[str]
emr_json: dict | None
emr_text: str | None
icd_suggestions: list
cpt_suggestions: list
rule_violations: list[str]
error: str | None
retry_count: int
```

**Steps:**
- [ ] Step 1: Write failing tests: node execution order (patient_rag → guideline_rag → context_merge → emr_generation → icd_coding → cpt_coding → rule_check → persist), state propagation (each node receives output of previous), error branch triggers `fail_safe_node`.
- [ ] Step 2: Implement `state.py` with `EMRGraphState` TypedDict.
- [ ] Step 3: Implement all node stubs in `nodes.py`. Each stub logs its node name and returns state unchanged (except setting `graph_node_name` for test assertions).
- [ ] Step 4: Implement `workflow.py`: compile graph with `StateGraph`, add nodes, add edges including the error branch (`retry_node` → `fail_safe_node` after max retries).
- [ ] Step 5: Run tests.
- [ ] Step 6: Commit.

---

### Task 3: RAG Ingestion Endpoint + Fixture Seed

**Purpose:** Build the ingestion pipeline and seed all test data into the DB and knowledge layer. After this task, Tasks 4 and 5 have real respiratory patient data and guideline chunks to work with.

**Pre-task checklist (before writing code):**
- [x] ✅ All CSV fixture files already updated to respiratory scope (Asthma/COPD/CAP, `primary_language=en-US`, `encounter_context` column, `providers.csv` created). Located in `fast-doc/docs/fixtures/` — copy to `fixtures/csv/` in project repo before running seed.
- [x] ✅ All 5 guideline PDFs already downloaded to `fast-doc/docs/guidelines/` — copy to `fixtures/guidelines/` in project repo:
  - `GINA-Summary-Guide-2025.pdf` (2.5 MB)
  - `GINA-Severe-Asthma-Guide-2025.pdf` (1.5 MB)
  - `GINA-Strategy-Report-2025.pdf` (11 MB)
  - `GOLD-Pocket-Guide-2025.pdf` (12 MB)
  - `GOLD-Report-2025.pdf` (16 MB)
- [ ] Verify column names in CSV files match ORM model fields exactly before running seed.

**Ingestion architecture（三层设计）：**

```
Layer 1 — 核心管道（chunk + embed + persist）
  MarkdownIngestionService.ingest_markdown(markdown, source_namespace, ...)
      └── [可选] ImageEnricher.enrich()  ← 检测到 ![image](url) 时自动触发
      └── DocumentChunker.split_markdown()
      └── SHA256 dedup
      └── llm_adapter.embed()
      └── persist KnowledgeDocument + KnowledgeChunk[]

Layer 2 — 来源适配（将各种输入转为 markdown）
  GuidelineIngestionService.ingest_pdf()   ← MinerU 提取 → MarkdownIngestionService
  (v2) PatientDocIngestionService           ← MinerU OCR → MarkdownIngestionService

Layer 3 — API 入口
  POST /v1/rag/markdown   ← 直接上传 .md 文件或提交 markdown 字符串
  POST /v1/rag/index      ← 提交纯文本 content（已有，简化保留）
  scripts/seed_fixtures.py
  scripts/ingest_guidelines.py (Task 3.1)
```

**Files to create/modify:**
```
app/api/v1/endpoints/__init__.py
app/api/v1/endpoints/rag.py               ← POST /v1/rag/index (text)
                                             POST /v1/rag/markdown (markdown文件/字符串)
app/services/markdown_ingestion_service.py ← NEW: 核心共享管道（Layer 1）
app/services/rag_ingestion_service.py      ← 保留 POST /v1/rag/index 的简单文本路径
app/models/rag.py                          ← verify fields match schema plan
scripts/__init__.py
scripts/seed_fixtures.py                   ← load CSV → DB + ingest patient docs
fixtures/csv/patients.csv               ← respiratory patients (fixed)
fixtures/csv/patient_demographics.csv
fixtures/csv/providers.csv              ← new
fixtures/csv/encounters.csv             ← respiratory (fixed)
fixtures/csv/lab_reports.csv
fixtures/csv/lab_results.csv            ← respiratory markers (fixed)
fixtures/csv/medication_records.csv     ← respiratory drugs (fixed)
fixtures/csv/allergy_records.csv
fixtures/csv/diagnosis_records.csv      ← ICD J45/J44/J18 (fixed)
fixtures/guidelines/                    ← downloaded PDFs (gitignored, fetched on demand)
tests/api/__init__.py
tests/api/test_rag_index.py
tests/api/test_rag_markdown.py
tests/services/test_markdown_ingestion_service.py
```

**`markdown_ingestion_service.py` specification（Layer 1 核心）：**

```python
class MarkdownIngestionService:
    """
    Universal markdown → RAG pipeline. Used by:
    - POST /v1/rag/markdown  (direct markdown import)
    - GuidelineIngestionService (after MinerU extraction)
    - PatientDocIngestionService (v2, after MinerU OCR)

    Auto-detects ![image](url) tags and routes through ImageEnricher when present.
    """
    EMBED_BATCH_SIZE = 10

    async def ingest_markdown(
        self,
        markdown: str,
        source_namespace: str,       # "patient" | "guideline"
        title: str,
        version: str = "",           # e.g. "GOLD-2025", "patient-upload-2026-04"
        effective_from: date | None = None,
        patient_id: str | None = None,   # required when source_namespace="patient"
        metadata_extra: dict | None = None,  # merged into each chunk's metadata_json
        reingest: bool = False,      # if True: delete existing chunks by document_id first
        enrich_images: bool = True,  # run ImageEnricher if markdown contains image tags
    ) -> dict:
        """
        Returns: {document_id, total_chunks, new_chunks, skipped_duplicates,
                  images_described, skipped_images}
        """
        # 1. Validate: patient_id required when source_namespace="patient"
        # 2. If reingest=True: DELETE KnowledgeChunk WHERE document_id = existing doc
        # 3. Auto-detect images: re.search(r'!\[image\]\(http', markdown)
        #    If images present AND enrich_images=True:
        #      → ImageEnricher.enrich(markdown) [calls Qwen-VL per clinical image]
        #    Else if images present AND enrich_images=False:
        #      → ImageEnricher.enrich(markdown, enabled=False) [placeholder replacement]
        # 4. DocumentChunker.split_markdown(enriched_markdown)
        #    → [(section_title, chunk_text), ...]
        # 5. For each chunk: SHA256 dedup (skip if hash in DB)
        # 6. Batch embed via llm_adapter.embed(batch_size=EMBED_BATCH_SIZE)
        # 7. INSERT KnowledgeDocument
        # 8. INSERT KnowledgeChunk[] with metadata_json:
        #    {"section_title": ..., "source_title": title, "version": version,
        #     "has_image_description": bool, **metadata_extra}
```

**`POST /v1/rag/markdown` endpoint specification：**

```python
# Request (supports two modes):
# Mode A — JSON body with markdown string:
{
  "source_namespace": "guideline",      # required: "patient" | "guideline"
  "title": "GOLD Pocket Guide 2025",    # required
  "markdown": "# Section\n...",         # required: markdown content string
  "version": "GOLD-2025",              # optional
  "effective_from": "2025-01-01",      # optional (ISO date)
  "patient_id": null,                  # required when source_namespace="patient"
  "reingest": false,                   # optional, default false
  "enrich_images": true                # optional, default true
}

# Mode B — Multipart file upload:
# POST /v1/rag/markdown with multipart/form-data
# Fields: source_namespace, title, [version], [patient_id], [reingest], [enrich_images]
# File: markdown_file (.md file)

# Response:
{
  "document_id": "uuid",
  "total_chunks": 42,
  "new_chunks": 40,
  "skipped_duplicates": 2,
  "images_described": 5,
  "skipped_images": 3
}
```

**Steps:**
- [ ] Step 1: Fix all CSV fixtures per the pre-task checklist above. Verify column names match schema plan exactly.
- [ ] Step 2: Write failing tests for `MarkdownIngestionService`:
  - Plain text markdown (no images) → creates correct `KnowledgeDocument` + N `KnowledgeChunk` rows.
  - Markdown with `![image](https://cdn-mineru...)` tags + `enrich_images=True` → ImageEnricher called, `has_image_description=true` on relevant chunks.
  - Markdown with images + `enrich_images=False` → no VL calls, placeholder text used.
  - `reingest=True` → old chunks deleted by `document_id`, new set created.
  - `source_namespace="patient"` without `patient_id` → raises `ValueError`.
  - SHA256 dedup: ingest same markdown twice → second run returns `new_chunks=0`.
  - `metadata_extra` fields appear in every chunk's `metadata_json`.
- [ ] Step 3: Implement `markdown_ingestion_service.py`. This is the shared core used by all ingestion paths.
- [ ] Step 4: Write failing API tests for `POST /v1/rag/markdown`:
  - JSON mode: guideline namespace → 201 with `document_id` and `chunk_count`.
  - Multipart mode: upload `.md` file → same response shape.
  - Missing `patient_id` for patient namespace → 422.
  - `source_namespace` invalid value → 422.
- [ ] Step 5: Implement `POST /v1/rag/markdown` endpoint (both JSON and multipart modes).
- [ ] Step 6: Write failing API tests for `POST /v1/rag/index` (existing text endpoint — keep minimal):
  - Required fields: `source_namespace`, `content`, `title`.
  - `source_namespace=patient` without `source_ref_id` → 422.
- [ ] Step 7: Implement `rag_ingestion_service.py` (thin wrapper: plain text → single chunk or pass to `MarkdownIngestionService`).
- [ ] Step 8: Implement `scripts/seed_fixtures.py`:
  - Read all CSV files from `fixtures/csv/`, insert into DB in migration order (patients → providers → encounters → labs → meds → allergies → diagnoses).
  - For each patient's lab reports, build markdown text from `lab_reports` + `lab_results` rows, then call `MarkdownIngestionService.ingest_markdown()` **directly** (not via HTTP) with `source_namespace="patient"`, `patient_id=<id>`, `metadata_extra={"abnormal_flag": ..., "report_time": ..., "encounter_id": ...}`.
  - ⚠️  Do NOT call `POST /v1/rag/markdown` via HTTP from this script — the service may not be running. Import and instantiate `MarkdownIngestionService` directly.
  - **Do NOT ingest guideline PDFs here.** Run `scripts/ingest_guidelines.py` (Task 3.1) separately after seed completes.
- [ ] Step 9: Run seed script against test DB. Verify row counts.
- [ ] Step 10: Run API tests.
- [ ] Step 11: Commit.

---

### Task 3.1: MinerU Service + Guideline PDF Extraction & RAG Ingestion

**Purpose:** Build a shared `MinerUService` for document extraction (PDF + images), then use it to ingest clinical guidelines into the knowledge layer. This service will be reused in later tasks for patient lab report and paper EMR extraction.

**Why MinerU over pypdf:**
GINA/GOLD guidelines contain multi-column layouts, treatment algorithm tables (e.g. asthma Step 1–5, GOLD ABCD matrix), and clinical dosing tables. pypdf loses column order and table structure — MinerU preserves them as clean Markdown. Since this same service handles patient-side scanned documents (lab reports, paper EMR images with OCR), centralising on MinerU avoids maintaining two extraction paths.

**Design reference (from MediCareAI):**
- `mineru_service.py`: MinerU API call pattern, async task submission + polling — **reuse and adapt directly**.
- `kb_vectorization_service.py`: `DocumentChunker` (hierarchical separator splitting + small-chunk merge + SHA256 dedup) — **reuse pattern**.
- `kb_vectorization_service.py`: `hybrid_search` with RRF fusion — **reuse pattern** in `guideline_rag_service` (Task 5).

**Scope of this task vs. future tasks:**

| Use case | This task (3.1) | Future task |
|----------|----------------|-------------|
| Guideline PDFs → `knowledge_chunks` (guideline) | ✅ | — |
| Patient lab report PDF/image → `knowledge_chunks` (patient) | — | Task 3 seed script (basic); full upload API in v2 |
| Paper EMR image (OCR) → `knowledge_chunks` (patient) | — | v2 |

> **MinerU as shared infrastructure**: `MinerUService` is instantiated in Task 3.1 and will be called from the patient document upload path in later versions. Design it as a standalone service, not tied to guideline logic.

**PDF files to ingest (in `fast-doc/docs/guidelines/`):**

| File | Size | Priority | Notes |
|------|------|----------|-------|
| `GINA-Summary-Guide-2025.pdf` | 2.5 MB | ✅ P0 | Asthma management overview |
| `GINA-Severe-Asthma-Guide-2025.pdf` | 1.5 MB | ✅ P0 | Severe/difficult-to-treat asthma |
| `GOLD-Pocket-Guide-2025.pdf` | 12 MB | ✅ P0 | COPD quick reference |
| `GINA-Strategy-Report-2025.pdf` | 11 MB | ✅ P0 | Full asthma strategy (Token API 支持 ≤200MB) |
| `GOLD-Report-2025.pdf` | 16 MB | ✅ P0 | Full COPD report (Token API 支持 ≤200MB) |

> **全部 5 个 PDF 均在 MVP 中处理**。Token API (精准解析) 支持最大 200MB / 600页，无需再区分"大文件"和"小文件"。

**Full pipeline architecture:**

```
                    ┌─────────────────────────────────────┐
                    │  Layer 2 — Source Adapters          │
                    │                                     │
  PDF File ─────►  │  GuidelineIngestionService          │
  (MinerU API)     │    .ingest_pdf()                    │
                   │     └─► MinerUService               │
                   │           .extract_to_markdown()     │
                   │           [Token-based 精准解析 API] │
                   │           ├─ local: batch upload PUT │
                   │           └─ remote: URL submission  │
                   └──────────────┬──────────────────────┘
                                  │ raw_markdown (with CDN image tags)
                                  ▼
                   ┌─────────────────────────────────────┐
                   │  Layer 1 — MarkdownIngestionService  │
                   │                                      │
                   │  [1] Auto-detect ![image](url) tags  │
                   │      enrich_images=True?             │
                   │       YES ──► ImageEnricher.enrich() │
                   │               ├─ DECORATIVE → remove │
                   │               └─ CLINICAL → Qwen-VL  │
                   │                  describe_image()    │
                   │       NO  ──► placeholder text only  │
                   │                                      │
                   │  [2] DocumentChunker.split_markdown()│
                   │       ├─ ## / ### heading boundaries │
                   │       ├─ \n\n paragraph boundaries   │
                   │       ├─ 1000-char / 200-char overlap│
                   │       └─ merge chunks < 100 chars    │
                   │                                      │
                   │  [3] SHA256 dedup (skip existing)    │
                   │                                      │
                   │  [4] llm_adapter.embed(batch=10)     │
                   │       Qwen text-embedding-v3, 1024d  │
                   │                                      │
                   │  [5] DB persist                      │
                   │       INSERT KnowledgeDocument        │
                   │       INSERT KnowledgeChunk[]        │
                   │         metadata_json:               │
                   │           section_title, source_file │
                   │           version, guideline_type    │
                   │           has_image_description:bool │
                   └──────────────────────────────────────┘

  ─────────── same Layer 1 called by ──────────────────────
  POST /v1/rag/markdown  ← pre-converted .md file / markdown string
                             (guideline or patient namespace)
  scripts/seed_fixtures  ← patient lab text as markdown
  PatientDocIngestion    ← v2, after MinerU OCR
```

> **MinerU CDN URL 过期风险**：MinerU 提取后的 `![image](cdn-url)` URL 具有时效性（按日期路径）。`MarkdownIngestionService` 必须在收到 `raw_markdown` 后立即调用 `ImageEnricher`，不能将图片描述延迟到后续步骤。
>
> **同样适用于患者文档（v2）**：患者化验报告 / 纸质 EMR 图片走相同管道：MinerU OCR → `MarkdownIngestionService`（`enrich_images=True`，将化验数值/异常标记转为文字）→ PatientRAG。`MinerUService` + `MarkdownIngestionService` 作为共享基础设施。

**New config keys (add to `app/core/config.py`):**
```python
MINERU_API_KEY: str                    # Bearer token from mineru.net (精准解析 API)
MINERU_SINGLE_URL: str = "https://mineru.net/api/v4/extract/task"
MINERU_BATCH_UPLOAD_URL: str = "https://mineru.net/api/v4/file-urls/batch"
MINERU_SINGLE_POLL_URL: str = "https://mineru.net/api/v4/extract/task/{task_id}"
MINERU_MODEL_VERSION: str = "vlm"     # vlm (recommended) | pipeline | MinerU-HTML
MINERU_LANGUAGE: str = "en"           # en for medical guidelines; ch for Chinese docs
MINERU_POLL_INTERVAL: int = 10        # seconds between polls (large PDFs take longer)
MINERU_MAX_WAIT: int = 900            # 15 min for 600-page documents
QWEN_VL_MODEL: str = "qwen-vl-max"   # vision-language model for image description
IMAGE_DESCRIPTION_ENABLED: bool = True  # set False to skip VL calls (faster testing)
# Removed: PUBLIC_FILE_URL — no longer needed; local files upload directly via batch API
```

**Files to create/modify:**

```
app/core/config.py                            ← add MinerU + VL model config keys
app/services/mineru_service.py                ← MinerU Token API client
app/services/image_enricher.py               ← parse images → classify → Qwen-VL → replace
app/services/document_chunker.py              ← DocumentChunker (adapted from MediCareAI)
app/services/markdown_ingestion_service.py    ← (created in Task 3) — used here as Layer 1
app/services/guideline_ingestion_service.py   ← MinerU → MarkdownIngestionService
scripts/ingest_guidelines.py                  ← CLI: ingest 5 PDFs
tests/services/test_mineru_service.py         ← mock MinerU API responses
tests/services/test_image_enricher.py         ← mock Qwen-VL responses
tests/services/test_document_chunker.py
tests/services/test_guideline_ingestion_service.py
```

> **注意**：`markdown_ingestion_service.py` 在 Task 3 中创建，Task 3.1 直接调用。`serve_local_files.py` 不再需要（Token API 支持直传）。

**`mineru_service.py` specification (Token-based 精准解析 API):**

```python
import zipfile, io

class MinerUService:
    """
    Shared extraction service for guidelines, lab reports, and paper EMR images.
    Uses MinerU 精准解析 API (Token-based): supports ≤200MB / ≤600 pages.
    All requests use: Authorization: Bearer {MINERU_API_KEY}
    """

    async def extract_to_markdown(
        self,
        file_path: str,           # local file path OR public https:// URL
        is_ocr: bool = True,      # True for scanned docs / image PDFs
        enable_table: bool = True,
        language: str = "en",     # "en" for medical guidelines
        timeout: int = 900,
    ) -> str:
        """
        Submit file to MinerU and return extracted Markdown text.
        Raises MinerUError on failure (timeout, auth error, API error).

        Flow for LOCAL FILE:
          1. POST /api/v4/file-urls/batch  →  get {batch_id, file_urls: [upload_url]}
          2. PUT upload_url with file bytes  (no Auth header on PUT)
          3. Poll GET /api/v4/extract-results/batch/{batch_id}
          4. On file state="done": download full_zip_url ZIP
          5. Extract full.md from ZIP → return text

        Flow for REMOTE URL:
          1. POST /api/v4/extract/task  →  get {task_id}
          2. Poll GET /api/v4/extract/task/{task_id}
          3. On state="done": download full_zip_url ZIP
          4. Extract full.md from ZIP → return text
        """

    async def _submit_local_file(self, file_path: str, **kwargs) -> str:
        """
        Upload local file via batch upload API.
        POST /api/v4/file-urls/batch  →  PUT file to pre-signed URL  →  return batch_id
        Payload: {"files": [{"name": filename, "is_ocr": ..., "data_id": ...}],
                  "model_version": "vlm", "enable_table": true, "language": "en"}
        Note: upload_link has 24-hour validity; PUT must NOT include Content-Type header.
        """

    async def _submit_url(self, url: str, **kwargs) -> str:
        """
        Submit remote URL for extraction.
        POST /api/v4/extract/task  →  return task_id
        Payload: {"url": url, "model_version": "vlm", "is_ocr": true,
                  "enable_table": true, "language": "en"}
        """

    async def _poll_single(self, task_id: str, timeout: int) -> str:
        """
        Poll GET /api/v4/extract/task/{task_id} until state="done".
        States: pending → running (has extract_progress) → done | failed
        On done: return full_zip_url
        """

    async def _poll_batch(self, batch_id: str, timeout: int) -> str:
        """
        Poll GET /api/v4/extract-results/batch/{batch_id}.
        Batch file states (in order): waiting-file → pending → running → done | failed
          - waiting-file: MinerU not yet detected the PUT upload; keep polling
          - pending: file queued for extraction
          - running: extraction in progress (has extract_progress)
          - done: full_zip_url available
          - failed: raise MinerUError with err_msg
        Since we upload one file at a time in ingest_pdf(), check extract_result[0] only.
        On done: return full_zip_url from extract_result[0].full_zip_url
        """

    async def _download_markdown_from_zip(self, zip_url: str) -> str:
        """
        Download full_zip_url ZIP via httpx, extract full.md, return content.
        ZIP structure: full.md (Markdown result), content_list.json,
                       layout.json, *_model.json
        Images in full.md are cdn-mineru CDN URLs (same as before).
        """
        # GET zip_url → bytes → zipfile.ZipFile(io.BytesIO(bytes))
        # → read "full.md" → return as str

class MinerUError(Exception):
    """Raised when MinerU extraction fails or times out."""
```

**`image_enricher.py` specification:**

```python
import re

DECORATIVE_SIGNALS = [
    "board of directors", "science committee", "editorial", "admin",
    "acknowledgement", "references", "global initiative", "copyright",
]
CLINICAL_SIGNALS = [
    "grade", "assessment", "spirometry", "management", "treatment",
    "diagnosis", "exacerbation", "oxygen", "pharmacolog", "classification",
    "prescription", "surgical", "interventional", "therapy", "cycle",
]

class ImageEnricher:
    """
    Replace MinerU image tags in markdown with Qwen-VL-generated text descriptions.
    Decorative images (covers, logos) are removed. Clinical diagrams are described.
    Must be called immediately after MinerU extraction — CDN URLs expire.
    """

    def __init__(self, llm_adapter, enabled: bool = True):
        self.llm_adapter = llm_adapter
        self.enabled = enabled  # set False in tests to skip VL calls

    async def enrich(self, markdown: str) -> str:
        """
        Parse all ![image](url) tags, classify, and replace with text.
        Returns enriched markdown with no remaining image tags.
        """
        lines = markdown.split('\n')
        enriched = []
        current_heading = "General"
        image_index = 0

        for line in lines:
            heading_match = re.match(r'^(#{1,3})\s+(.+)', line)
            if heading_match:
                current_heading = heading_match.group(2).strip()
                enriched.append(line)
                continue

            img_match = re.match(r'!\[image\]\((https://[^\)]+)\)', line.strip())
            if img_match:
                image_index += 1
                url = img_match.group(1)

                if self._is_decorative(current_heading, image_index):
                    # Remove decorative images entirely
                    continue

                if not self.enabled:
                    enriched.append(f'[IMAGE — {current_heading}]')
                    continue

                description = await self.llm_adapter.describe_image(
                    url, context_hint=current_heading
                )
                enriched.append(
                    f'\n[IMAGE DESCRIPTION — {current_heading}]:\n{description}\n'
                )
            else:
                enriched.append(line)

        return '\n'.join(enriched)

    def _is_decorative(self, heading: str, image_index: int) -> bool:
        """First 3 images (cover/logo) and headings matching decorative signals are skipped."""
        if image_index <= 3:
            return True
        h = heading.lower()
        if any(s in h for s in DECORATIVE_SIGNALS):
            return True
        return False
```

**`document_chunker.py` specification (adapted from MediCareAI `DocumentChunker`):**

```python
class DocumentChunker:
    """
    Chunk Markdown text into RAG-ready segments.
    Adapted from MediCareAI kb_vectorization_service.DocumentChunker.
    Key difference: treats ## / ### headings as hard section boundaries,
    so table content stays within its section chunk.
    """
    CHUNK_SIZE = 1000       # characters
    CHUNK_OVERLAP = 200
    MIN_CHUNK_SIZE = 100    # merge smaller chunks
    SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", ". ", " "]

    def split_markdown(self, markdown: str) -> list[tuple[str, str]]:
        """Returns list of (section_title, chunk_text) tuples."""

    def _extract_sections(self, markdown: str) -> list[tuple[str, str]]:
        """Split on ## / ### headings; fallback to ("General", full_text)."""

    def _split_section(self, title: str, text: str) -> list[tuple[str, str]]:
        """Split one section into chunks using SEPARATORS + character fallback."""

    @staticmethod
    def sha256(text: str) -> str:
        """SHA256 hash for deduplication."""
```

**`guideline_ingestion_service.py` specification:**

```python
class GuidelineIngestionService:
    EMBED_BATCH_SIZE = 10

    async def ingest_pdf(
        self,
        pdf_path: str,
        title: str,
        version: str,           # e.g. "GINA-2025", "GOLD-2025"
        effective_from: date,
        guideline_type: str,    # "asthma" | "copd"
        reingest: bool = False,
    ) -> dict:
        """
        PDF → MinerU → MarkdownIngestionService.
        Returns: {document_id, total_chunks, new_chunks, skipped_duplicates, images_described}
        """
        # 1. MinerUService.extract_to_markdown(pdf_path, is_ocr=True,
        #        enable_table=True, language="en")
        #    → raw_markdown (contains ![image](cdn-url) tags)
        #    ⚠️  MinerU CDN URLs expire — must call MarkdownIngestionService immediately
        # 2. MarkdownIngestionService.ingest_markdown(
        #        markdown=raw_markdown,
        #        source_namespace="guideline",
        #        title=title,
        #        version=version,
        #        effective_from=effective_from,
        #        patient_id=None,
        #        metadata_extra={"source_file": basename(pdf_path),
        #                        "guideline_type": guideline_type},
        #        reingest=reingest,
        #        enrich_images=True,   # Qwen-VL describes clinical diagrams
        #    )
        # 3. Return result from MarkdownIngestionService directly
```

**`scripts/ingest_guidelines.py` manifest:**

```python
GUIDELINE_MANIFEST = [
    {
        "file": "GINA-Summary-Guide-2025.pdf",        # 2.5 MB
        "title": "GINA Summary Guide 2025",
        "version": "GINA-2025",
        "effective_from": "2025-05-01",
        "guideline_type": "asthma",
    },
    {
        "file": "GINA-Severe-Asthma-Guide-2025.pdf",  # 1.5 MB
        "title": "GINA Severe Asthma Guide 2025",
        "version": "GINA-Severe-2025",
        "effective_from": "2025-05-01",
        "guideline_type": "asthma",
    },
    {
        "file": "GINA-Strategy-Report-2025.pdf",       # 11 MB — full strategy report
        "title": "GINA Strategy Report 2025",
        "version": "GINA-Strategy-2025",
        "effective_from": "2025-05-01",
        "guideline_type": "asthma",
    },
    {
        "file": "GOLD-Pocket-Guide-2025.pdf",          # 12 MB
        "title": "GOLD COPD Pocket Guide 2025",
        "version": "GOLD-2025",
        "effective_from": "2025-01-01",
        "guideline_type": "copd",
    },
    {
        "file": "GOLD-Report-2025.pdf",                # 16 MB — full COPD report
        "title": "GOLD COPD Report 2025",
        "version": "GOLD-Full-2025",
        "effective_from": "2025-01-01",
        "guideline_type": "copd",
    },
]
# Usage:
#   python scripts/ingest_guidelines.py --pdf-dir fast-doc/ [--reingest]
#       ← full pipeline: MinerU → ImageEnricher → MarkdownIngestionService
#
#   python scripts/ingest_guidelines.py --markdown-dir fast-doc/ [--reingest]
#       ← shortcut: skip MinerU, use pre-existing .md files (e.g. MinerU_markdown_*.md)
#         directly calls MarkdownIngestionService.ingest_markdown() with enrich_images=True
#         (still runs ImageEnricher to handle any CDN image tags)
#         Markdown filename must match pattern: *{pdf_title_slug}*.md
#
# All 5 PDFs processed via MinerU Token API (≤200MB limit, no file-size restriction).
# Large PDFs (GINA Strategy 11MB, GOLD Report 16MB) may take 5–15 min each.
# Script prints per-PDF progress (MinerU running page count) and final summary table.
```

**Steps:**

- [ ] Step 1: Add `MINERU_API_KEY`, `MINERU_API_URL`, `MINERU_POLL_INTERVAL`, `MINERU_MAX_WAIT`, `PUBLIC_FILE_URL`, `QWEN_VL_MODEL`, `IMAGE_DESCRIPTION_ENABLED` to `app/core/config.py`. Remove `pypdf` and `ftfy` from `pyproject.toml` (no longer needed). Run `uv sync`.
- [ ] Step 2: Write failing tests for `MinerUService` using `pytest-httpx` to mock MinerU API:
  - **Local file flow**: mock `POST /api/v4/file-urls/batch` → mock PUT upload (200) → mock batch poll `done` → mock ZIP download → returns markdown string.
  - **Remote URL flow**: mock `POST /api/v4/extract/task` → mock single poll `done` → mock ZIP download → returns markdown string.
  - **ZIP extraction**: mock ZIP bytes containing `full.md` with `![image](cdn-url)` tags → `_download_markdown_from_zip()` returns correct markdown.
  - **Auth error**: mock `POST` returning `{"code": "A0202"}` → raises `MinerUError("token invalid")`.
  - **Timeout**: poll never returns `"done"` within `MINERU_MAX_WAIT` → raises `MinerUError("timeout after Xs")`.
  - **Running progress**: mock `state=running` with `extract_progress.total_pages=50, extracted_pages=10` → logs progress, continues polling.
- [ ] Step 3: Implement `mineru_service.py` with `MinerUService` and `MinerUError`. Reference `MediCareAI/backend/app/services/mineru_service.py` for API call structure and polling pattern, but adapt: remove OSS/Alibaba dependency, use Token-based batch upload (`/api/v4/file-urls/batch`) for local files (no `tmpfiles.org`).
- [ ] Step 4: Write failing tests for `ImageEnricher` using `pytest-httpx` to mock Qwen-VL:
  - `enrich()` with markdown containing 5 images (3 decorative + 2 clinical) → decorative removed, clinical replaced with `[IMAGE DESCRIPTION — ...]` text.
  - First 3 images always removed regardless of heading.
  - `enrich()` with `enabled=False` → clinical images replaced with `[IMAGE — <heading>]` placeholder, no VL calls made.
  - Qwen-VL 429 → `RateLimitError` propagates.
  - Verify final markdown contains zero `![image]` tags.
- [ ] Step 5: Implement `image_enricher.py` with `ImageEnricher`. Use `llm_adapter.describe_image()` from Task 1.
- [ ] Step 6: Write failing tests for `DocumentChunker`:
  - `split_markdown()` on a string with 3 `##` headings → returns >= 3 groups with correct titles.
  - Long section (> CHUNK_SIZE chars) → split into multiple chunks, each <= CHUNK_SIZE.
  - Markdown table block stays within a single chunk (not split mid-row).
  - Input containing `[IMAGE DESCRIPTION — ...]` block stays within its section chunk.
  - `sha256()` is deterministic and returns 64-char hex string.
- [ ] Step 7: Implement `document_chunker.py`. Ensure Markdown table blocks are never split mid-table and `[IMAGE DESCRIPTION — ...]` blocks are treated as regular text.
- [ ] Step 8: Write failing tests for `GuidelineIngestionService`:
  - `ingest_pdf()` (mocked MinerU + mocked Qwen-VL) → creates 1 `KnowledgeDocument` + N chunks; chunks containing image descriptions have `metadata_json.has_image_description=true`.
  - Calling `ingest_pdf()` twice without `reingest=True` → zero new chunks (all deduped).
  - Calling `ingest_pdf()` with `reingest=True` → old chunks deleted via `document_id` (not title), fresh set created.
  - `IMAGE_DESCRIPTION_ENABLED=False` → ingest completes with placeholder text, no VL calls.
- [ ] Step 9: Implement `guideline_ingestion_service.py`.
- [ ] Step 10: Implement `scripts/ingest_guidelines.py` with the manifest above.
- [ ] Step 11: Run `python scripts/ingest_guidelines.py --pdf-dir fast-doc/` against test DB. Confirm:
  - 5 `KnowledgeDocument` rows with `source_namespace="guideline"`.
  - >= 500 `KnowledgeChunk` rows total across 5 PDFs (large reports produce more chunks).
  - Chunks with `has_image_description=true` present across multiple documents.
  - All chunks have `embedding_vector` with `EMBEDDING_DIM=1024` dimensions.
  - Large PDFs (GOLD Report 16MB, GINA Strategy 11MB) complete without timeout (`MINERU_MAX_WAIT=900`).
- [ ] Step 12: Run all tests.
- [ ] Step 13: Commit.

---

### Task 4: Route-1 PatientRAG

**Purpose:** Implement patient-scoped vector retrieval. Uses `knowledge_chunks.patient_id` B-tree pre-filter + cosine similarity.

**Files to create/modify:**
```
app/services/patient_rag_service.py
app/models/clinical.py                  ← verify LabResult.abnormal_flag field
tests/services/test_patient_rag_service.py
```

**Retrieval algorithm:**
1. Pre-filter: `WHERE patient_id = :patient_id AND is_active = TRUE`
2. Vector similarity: cosine distance on `embedding_vector`
3. Recency boost: multiply score by `1 / (1 + days_since_encounter * 0.05)` (weight recent encounters higher)
4. Abnormal-lab boost: multiply score by `1.3` if `metadata_json->>'abnormal_flag' = 'true'`
5. Return top-k (default k=5) with chunk text and metadata

**Integration test data dependency:** Requires Task 3 seed to be complete. Tests use fixture patients from `fixtures/csv/patients.csv` (respiratory: asthma/COPD/CAP). Confirm `knowledge_chunks` has patient-namespace rows before running.

**Steps:**
- [ ] Step 1: Write failing tests using seeded fixture patients:
  - `patient_id` hard filter: query patient A's chunks; assert patient B's chunks never appear.
  - Recency boost: seed two chunks for same patient at different encounter dates; assert newer chunk ranks higher.
  - Abnormal-lab boost: seed one chunk with `abnormal_flag=true` (e.g., FEV1 < 50% predicted); assert it surfaces in top-3 even with slightly lower vector score.
- [ ] Step 2: Implement `patient_rag_service.py` with the retrieval algorithm above. Use SQLAlchemy async session. Emit a `RetrievalLog` row after every retrieval.
- [ ] Step 3: Add abnormal-lab boost in ranking.
- [ ] Step 4: Run tests.
- [ ] Step 5: Commit.

---

### Task 5: Route-2 GuidelineRAG

**Purpose:** Implement guideline-scoped hybrid retrieval (keyword + vector). Scoped to respiratory guidelines for MVP.

**Files to create/modify:**
```
app/services/guideline_rag_service.py
app/models/rag.py                       ← verify KnowledgeDocument fields
tests/services/test_guideline_rag_service.py
```

**Retrieval algorithm:**
1. Pre-filter: `WHERE source_namespace='guideline' AND is_active=TRUE AND (effective_to IS NULL OR effective_to >= NOW())`
2. Keyword match: parameterized query `chunk_text ILIKE :kw` (where `:kw = f"%{keyword}%"`) — **never interpolate keywords directly into SQL string** (SQL injection risk). Run one query per keyword term with `OR` bindings, return binary match score (1 if any keyword hits, 0 otherwise) per chunk.
3. Vector similarity: cosine on `embedding_vector`
4. Score fusion: `final_score = 0.6 * vector_score + 0.4 * keyword_match_score` where `keyword_match_score` is the fraction of query terms matched (e.g., 2/3 terms matched = 0.67)
5. Fallback: if zero chunks pass keyword filter, skip keyword score (use vector-only ranking)
6. Return top-k (default k=5) with chunk text, document title, version

**Integration test data dependency:** Requires Task 3 seed to be complete, including GINA and GOLD PDF ingestion. Confirm `knowledge_chunks` has guideline-namespace rows (>= 50 chunks from GINA Summary + GOLD Pocket Guide) before running.

**Steps:**
- [ ] Step 1: Write failing tests using seeded guideline chunks:
  - Version filter: manually insert an expired chunk (`effective_to = yesterday`); assert it is excluded from results.
  - Keyword match: query with `"FEV1"` or `"bronchodilator"`; assert GOLD COPD chunks appear in top results.
  - Specialization: assert no non-respiratory documents appear (MVP constraint: all seeded guidelines are respiratory).
- [ ] Step 2: Implement `guideline_rag_service.py` with the hybrid retrieval algorithm above. Emit a `RetrievalLog` row after every retrieval.
- [ ] Step 3: Run tests.
- [ ] Step 4: Commit.

---

### Task 6: Context Merge + EMR Generation

**Purpose:** Merge patient and guideline context with conflict resolution, then generate the structured EMR note.

**Files to create/modify:**
```
app/services/context_merge_service.py
app/services/emr_service.py
app/api/v1/endpoints/emr.py             ← POST /v1/emr/generate
tests/services/test_context_merge_service.py
tests/api/test_emr_generate.py
```

**Conflict resolution rules:**
1. **Fact conflict** (same fact from patient and guideline disagrees): patient fact takes priority; add `"fact_conflict"` to `conflict_flags`.
2. **Time conflict** (two patient records disagree): newer encounter date takes priority; add `"time_conflict"` to `conflict_flags`.
3. **Guideline conflict** (two guideline chunks disagree): higher-grade guideline (from `metadata_json->>'evidence_grade'`) takes priority; add `"guideline_conflict"` to `conflict_flags`.

**EMR generation rules:**
- Prompt must be English-only. Reject if transcript language detected as non-English (simple heuristic: check for `\u4e00-\u9fff` CJK range; return 422 if found).
- Output must parse as valid `soap_json` (`{subjective, objective, assessment, plan}` all non-empty strings).
- Retry up to 2 times on parse failure before returning `fail_safe_node`.
- Store `context_trace_json` (merged context + conflict flags) in `EmrNote`.

**Provider-aware prompt construction（专科定制 Prompt）：**

`emr_service.py` 在构建 prompt 前，先通过 `encounter.provider_id` 查询 `providers` 表，提取以下字段注入 system prompt：

| `providers` 字段 | prompt 注入方式 |
|-----------------|----------------|
| `credentials` + `full_name` | system prompt 开头："You are assisting **Dr. Sarah Chen, MD**..." |
| `specialty` | 选择专科 SOAP 模板前缀（见下表） |
| `sub_specialty` | 在 assessment/plan 中额外强调该亚专科的关注点 |
| `prompt_style` | 控制输出风格：`standard`=标准门诊；`detailed`=完整病历；`concise`=急诊简要；`critical_care`=ICU |

**专科 prompt 模板映射（MVP 只需呼吸科，其余作为扩展预留）：**

```python
SPECIALTY_PROMPT_PREFIXES = {
    "pulmonology": (
        "Focus on respiratory function: document FEV1/FVC ratio, SpO2, dyspnea scale (mMRC), "
        "inhaler technique, exacerbation triggers, and GINA/GOLD guideline adherence in the plan."
    ),
    "cardiology": (
        "Focus on cardiac findings: document heart rate, rhythm, BP, EF if known, "
        "medication compliance, and ACC/AHA guideline adherence."
    ),
    # v2: add more specialties
}

SUB_SPECIALTY_ADDITIONS = {
    "critical_care": (
        "Patient is in a critical care setting. Include ventilator settings if applicable, "
        "GCS score, vasopressor requirements, and daily goals of care discussion."
    ),
    "general": "",  # no additional emphasis
}

PROMPT_STYLE_INSTRUCTIONS = {
    "standard":      "Generate a standard outpatient SOAP note.",
    "detailed":      "Generate a comprehensive SOAP note with full clinical reasoning and differential diagnosis.",
    "concise":       "Generate a brief SOAP note suitable for a fast-paced clinical setting. Be succinct.",
    "critical_care": "Generate an ICU-style SOAP note with emphasis on organ system review.",
}
```

**完整 system prompt 构建逻辑：**
```python
def _build_system_prompt(provider: Provider | None, encounter: Encounter) -> str:
    base = "You are a clinical documentation assistant."
    if provider:
        base = (
            f"You are assisting {provider.full_name}"
            + (f", {provider.credentials}" if provider.credentials else "")
            + (f", a {provider.specialty} specialist" if provider.specialty else "")
            + "."
        )
    style = PROMPT_STYLE_INSTRUCTIONS.get(
        getattr(provider, "prompt_style", "standard"), PROMPT_STYLE_INSTRUCTIONS["standard"]
    )
    specialty_prefix = SPECIALTY_PROMPT_PREFIXES.get(
        getattr(provider, "specialty", ""), ""
    )
    sub_specialty_addition = SUB_SPECIALTY_ADDITIONS.get(
        getattr(provider, "sub_specialty", ""), ""
    )
    return "\n".join(filter(None, [base, style, specialty_prefix, sub_specialty_addition]))
```

> **Fallback**: if `encounter.provider_id` is NULL or provider not found, use `"standard"` style with no specialty prefix.

**Steps:**
- [ ] Step 1: Write failing tests for merged context shape (correct keys), conflict flag propagation, and non-English input rejection.
- [ ] Step 2: Implement `context_merge_service.py` with the three conflict resolution rules.
- [ ] Step 3: Implement `emr_service.py`:
  - Load provider from `encounter.provider_id` (nullable, graceful fallback).
  - Build system prompt via `_build_system_prompt(provider, encounter)`.
  - Call `llm_adapter.chat()`, parse and validate `soap_json`, retry on failure.
  - Persist `EmrNote` with `context_trace_json` (includes `provider_id`, `prompt_style_used`) and `request_id`.
- [ ] Step 4: Write failing tests for provider-aware prompt:
  - Provider with `specialty="pulmonology"` → system prompt contains FEV1/FVC and GINA/GOLD references.
  - Provider with `prompt_style="detailed"` → system prompt requests full differential diagnosis.
  - `provider_id=None` → falls back to standard prompt without error.
  - Provider with `sub_specialty="critical_care"` → prompt includes GCS and ventilator language.
- [ ] Step 5: Implement `POST /v1/emr/generate` endpoint. Bind to LangGraph workflow (invoke graph, return state output).
- [ ] Step 6: Implement EMR JSON schema validation + retry logic.
- [ ] Step 7: Run tests.
- [ ] Step 8: Commit.

---

### Task 7: ICD/CPT Catalog + Coding Suggestions + Rule Engine

**Purpose:** Ingest coding catalogs and implement LLM-assisted code suggestion with deterministic post-check.

#### ICD/CPT 数据架构决策

ICD/CPT 数据在编码流程中扮演**两个角色**，MVP 和 v2 采用不同策略：

| 角色 | 描述 | MVP 方案 | v2 方案 |
|------|------|---------|---------|
| **候选发现** | "患者喘息+FEV1↓，哪些 J 码可能适用？" | SQL 关键词过滤 → 注入 Prompt | 向量 RAG（全量 70000+ 码） |
| **精确验证** | "J44.1 在当前版本中存在且有效吗？" | `icd_catalog` 表精确查询 | 同左 |

**MVP 选择 SQL 而非 RAG 的原因**：J00–J99 呼吸科章节约 400 条，可直接通过 SQL 关键词过滤注入 Prompt（30 条候选），无需额外向量索引。当 v2 扩展到全量 ICD（70000+ 条）时，才需要 coding_reference RAG 路由。

**完整编码流程：**

```
SOAP note (from EMR generation node)
    │
    ▼ [1] keyword_extractor  (non-LLM, regex/stopword)
         提取 3–5 个关键临床术语，e.g. ["obstruction", "exacerbation", "COPD"]
    │
    ▼ [2] SQL candidate selection
         SELECT code, title, chapter FROM icd_catalog
         WHERE catalog_version = 'ICD-10-CM-2025'
           AND (title ILIKE '%obstruct%' OR title ILIKE '%exacerbat%' OR title ILIKE '%copd%')
         LIMIT 30
         → 30 条候选 ICD 码列表
    │
    ▼ [3] LLM coding prompt  (llm_adapter.chat)
         输入: SOAP note + patient context + 30条候选码 + guideline evidence
         输出: JSON list [{code, rank, confidence, rationale}]
    │
    ▼ [4] Rule Engine        (deterministic, post-LLM)
         - Block: code not in icd_catalog for current version
         - Block: effective_to < today
         - Flag: CPT modifier not in modifier_rules_json
         - All: force status = needs_review
    │
    ▼ [5] Persist
         CodingSuggestion + CodingEvidenceLink rows
```

#### 数据来源

**ICD-10-CM 2025（免费，CMS 官方）：**
- ✅ **已下载并处理完毕**，文件在 `fast-doc/docs/medical-codes/` 目录
- 原始来源：[CDC/NCHS FTP](https://ftp.cdc.gov/pub/health_statistics/nchs/Publications/ICD10CM/2025/)
- **MVP 直接使用** `icd10cm_J_respiratory_2025.tsv`（354 条，4 列：`code, description, chapter, catalog_version`）
- **全量备用** `icd10cm_full_2025.tsv`（23,082 条，v2 扩展全科室时使用）
- 关键呼吸科子组：J44（COPD，5 码）、J45（哮喘，18 码）、J18/J15/J12（肺炎，各 5–14 码）、J96（呼吸衰竭，12 码）
- `catalog_ingestion_service` 读取此 TSV，按 `(code, catalog_version)` upsert 到 `icd_catalog`
- v2：加载完整 XML（含 includes/excludes/notes），并做向量化 coding_reference RAG

**CPT（✅ 数据已到位，全量 23,089 条）：**
- 源文件：`fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv`（9 列 CSV，含全量 AMA CPT 代码）
- 字段映射：`CPTCode → code` (strip), `CPTName → short_name`, `CPTDesc → description` (空时 fallback CPTName), `AvgFee → avg_fee` (0 → NULL), `RVU → rvu` (0 → NULL)
- `cpt_catalog` 表已在 Schema 计划中补充 `short_name`, `description`, `avg_fee`, `rvu` 字段（migration `004` 须包含）
- `ClinicID / DoctorID / SuperBill / Status` 为 PMS 导出字段，全为 0，ingestion 时忽略
- `catalog_ingestion_service.ingest_cpt()` 直接读取此 CSV，过滤后 upsert 到 `cpt_catalog`
- `catalog_version = "CPT-2026-04"`

**CPT ingestion 数据清洗规则（已 review 确认）：**

| 问题 | 数量 | 处理方式 |
|------|------|---------|
| CPTCode 含尾部空格 | 7,657 条 | `.strip()` |
| deleted 码（嵌在 CPTName） | 3,801 条 | `"deleted" in CPTName.lower()` → 跳过 |
| 非标准本地扩展码（>5 字符） | 5 条（99212P1 等） | `len(code) > 5` → 跳过 |
| CPTDesc 为空 | 9 条 | fallback 用 CPTName |
| AvgFee / RVU 为字符串 | 全部 | 转 float，`"0.0000"` → `None` |

**MVP ingestion 范围（呼吸科）：**
- 全量加载所有 active 代码（19,288 条），不限制章节
- 理由：CPT 无章节概念，代码号段分散（94xxx 肺功能、99xxx E&M、31xxx 支气管镜等），全量加载后通过 SQL keyword filter 候选即可

**Pre-task checklist：**
- [x] ICD-10-CM 数据已就绪：`fast-doc/docs/medical-codes/icd10cm_J_respiratory_2025.tsv`（354 条 J 章节）
- [x] CPT 数据已就绪：`fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv`（23,089 条，含全量 CPT）

**Files to create/modify:**
```
app/models/coding.py                         ← verify IcdCatalog, CptCatalog fields
app/services/catalog_ingestion_service.py    ← load ICD txt + CPT CSV → icd_catalog/cpt_catalog
app/services/keyword_extractor.py           ← non-LLM: extract clinical terms from SOAP note
app/services/coding_service.py              ← SQL candidate → LLM → parse → persist
app/services/rule_engine.py                 ← deterministic post-LLM validator
app/api/v1/endpoints/coding.py              ← POST /v1/coding/icd/suggest
                                               POST /v1/coding/cpt/suggest
scripts/ingest_catalogs.py                  ← NEW: CLI to load ICD + CPT into DB
fast-doc/docs/medical-codes/icd10cm_J_respiratory_2025.tsv  ← ✅ already generated, 354 J codes
fast-doc/docs/medical-codes/icd10cm_full_2025.tsv          ← ✅ already generated, 23,082 all codes
fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv       ← ✅ CPT全量数据，23,089 条，含 AvgFee/RVU
tests/services/test_catalog_ingestion_service.py
tests/services/test_keyword_extractor.py
tests/api/test_coding_suggest.py
```

**`scripts/ingest_catalogs.py` specification：**
```python
# Usage:
#   python scripts/ingest_catalogs.py --icd-file fast-doc/docs/medical-codes/icd10cm_J_respiratory_2025.tsv
#   python scripts/ingest_catalogs.py --cpt-file fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv
#   python scripts/ingest_catalogs.py --all   ← runs both ICD + CPT
#
# Run this ONCE after Task 7 Step 3 (before coding tests).
# Idempotent: safe to re-run (UPSERT ON CONFLICT).
# Must be run BEFORE any coding_service tests that query icd_catalog/cpt_catalog.
#
# Execution order in overall setup:
#   1. alembic upgrade head
#   2. python scripts/seed_fixtures.py           (patient data + patient RAG chunks)
#   3. python scripts/ingest_guidelines.py --pdf-dir fixtures/guidelines/   (guideline RAG)
#   4. python scripts/ingest_catalogs.py --all   (ICD + CPT catalogs for coding)
```

**`keyword_extractor.py` specification:**
```python
class KeywordExtractor:
    """Non-LLM extraction of clinical terms from SOAP note for catalog pre-filtering.
    No LLM call here — this is a cheap SQL pre-filter step, not semantic search."""

    RESPIRATORY_STOPWORDS = {"the", "with", "and", "for", "of", "patient", "history"}
    RESPIRATORY_SYNONYMS = {
        "copd": ["obstruct", "chronic obstructive"],
        "asthma": ["wheez", "bronchospasm", "reversible obstruct"],
        "pneumonia": ["consolidat", "infiltrat", "infect"],
        "exacerbation": ["exacerbat", "worsening", "acute"],
    }

    def extract(self, soap_json: dict) -> list[str]:
        """Extract 3–5 search terms from SOAP assessment + plan fields."""
        # 1. Concatenate assessment + plan text
        # 2. Tokenize, lowercase, remove stopwords
        # 3. Expand known synonyms
        # 4. Return top 5 terms by frequency
```

**`catalog_ingestion_service.py` specification:**
```python
class CatalogIngestionService:

    async def ingest_icd(
        self,
        tsv_file_path: str,           # path to icd10cm_J_respiratory_2025.tsv
        chapter_filter: str = "J",    # MVP: respiratory chapter only
        catalog_version: str = "ICD-10-CM-2025",
    ) -> dict:
        """
        Parse tab-delimited ICD TSV (columns: code, description, chapter, catalog_version),
        filter by chapter prefix, upsert into icd_catalog.
        Idempotent: UPSERT ON CONFLICT (code, catalog_version) DO UPDATE SET description=...
        Returns: {total_parsed, loaded, skipped_existing}
        """

    async def ingest_cpt(
        self,
        csv_file_path: str,           # path to Ref_CPT_202604091710.csv
        catalog_version: str = "CPT-2026-04",
    ) -> dict:
        """
        Load CPT CSV into cpt_catalog with data cleaning:
        1. Strip CPTCode whitespace
        2. Skip if "deleted" in CPTName (case-insensitive)
        3. Skip if len(code) > 5 (non-standard local codes: 99212P1, 99213GT etc.)
        4. description = CPTDesc.strip() or CPTName (fallback if empty)
        5. avg_fee = float(AvgFee) if AvgFee not in ('', '0', '0.0000') else None
        6. rvu = float(RVU) if RVU not in ('', '0') else None
        7. Ignore: ClinicID, DoctorID, SuperBill, Status fields
        Idempotent: UPSERT ON CONFLICT (code, catalog_version) DO UPDATE SET description=...
        Returns: {total_parsed, loaded, skipped_deleted, skipped_nonstandard}
        """

    def _is_deleted(self, cpt_name: str) -> bool:
        return "deleted" in cpt_name.lower()

    def _is_nonstandard(self, code: str) -> bool:
        # Local PMS extension codes (>5 chars after strip)
        return len(code) > 5
```

**Rule engine checks (deterministic, post-LLM):**
- Block: code not found in `icd_catalog` for current `catalog_version` → status `rejected`
- Block: `effective_to < today` → status `rejected`
- Block: LLM returned code outside loaded chapter (non-J code in respiratory MVP) → status `rejected`
- Flag: CPT modifier not in `modifier_rules_json` → add warning to `rationale`
- All outputs: default `status = needs_review` regardless of confidence

**Steps:**
- [ ] Step 1: 确认数据文件：ICD `fast-doc/docs/medical-codes/icd10cm_J_respiratory_2025.tsv`（354 条）、CPT `fast-doc/docs/medical-codes/Ref_CPT_202604091710.csv`（23,089 条）均已就绪。
- [ ] Step 2: Write failing tests:
  - `catalog_ingestion_service.ingest_icd()`: 加载 354 条 J 章节，re-run 幂等（无重复）。
  - `catalog_ingestion_service.ingest_cpt()`: 过滤后约 19,280 条入库（deleted 3,801 + nonstandard 5 被跳过）；re-run 幂等；`AvgFee="0.0000"` 映射为 `None`；空 CPTDesc 用 CPTName 替代；code 无尾部空格。
  - `keyword_extractor`: SOAP note with "COPD exacerbation" → returns terms including "obstruct" and "exacerbat".
  - `coding_service`: suggestion fails if catalog is empty (returns error); every suggestion has ≥1 `CodingEvidenceLink`.
  - `rule_engine`: rejects non-existent code; rejects expired code; forces `needs_review` on all outputs.
- [ ] Step 3: Implement `catalog_ingestion_service.py`. Run ICD ingestion against test DB — confirm ~354 J-chapter rows loaded (actual TSV row count).
- [ ] Step 4: Implement `keyword_extractor.py`.
- [ ] Step 5: Implement `coding_service.py`: keyword extract → SQL candidate (30 codes) → build prompt → `llm_adapter.chat()` → parse JSON output → create `CodingSuggestion` + `CodingEvidenceLink`.
- [ ] Step 6: Implement `rule_engine.py`. Wire into `coding_service` as a mandatory post-step.
- [ ] Step 7: Run all tests.
- [ ] Step 8: Commit.

---

### Task 8: Auditability & Observability

**Purpose:** Ensure every request is traceable end-to-end and all PHI access events are logged.

**Files to create/modify:**
```
app/models/ops.py                       ← verify LlmCall, AuditEvent fields
app/services/audit_service.py           ← emit_audit_event() helper
app/services/llm_adapter.py            ← add LlmCall persistence on every call
tests/services/test_observability.py
tests/services/test_audit_service.py
```

**Traceability requirements:**
- Every `llm_adapter.chat()` and `llm_adapter.embed()` call must persist a `LlmCall` row with `graph_node_name`, `request_id`, `latency_ms`, `prompt_tokens`, `completion_tokens`.
- Every `RetrievalLog` row must have `request_id` set.
- Every `CodingEvidenceLink` must have `evidence_route` set.
- Every `EmrNote` must have `request_id` set.

**Audit event requirements:**
- `ssn_full_access`: emitted when `ssn_encrypted` is decrypted. Must include `actor_id`, `actor_role`, `access_reason`, `request_id`, `patient_id`.
- `note_finalized`: emitted when `emr_notes.is_final` is set to TRUE.
- `coding_accepted` / `coding_rejected`: emitted when `coding_suggestions.status` changes.
- `audit_events` table: application DB role has INSERT-only; no UPDATE/DELETE.

**Steps:**
- [ ] Step 1: Write failing tests: `LlmCall` row created with correct `graph_node_name` for each LangGraph node, `RetrievalLog` has `request_id`, `AuditEvent` emitted on SSN decryption.
- [ ] Step 2: Add `LlmCall` persistence to `llm_adapter.py`. Use `request_id` from graph state (passed as argument).
- [ ] Step 3: Implement `audit_service.py` with `emit_audit_event(event_type, actor_id, ...)` async function. Must be called before returning the decrypted SSN value; call failure should raise, not swallow.
- [ ] Step 4: Add `evidence_route` to all `CodingEvidenceLink` creation paths.
- [ ] Step 5: Run tests.
- [ ] Step 6: Commit.

---

### Task 9: Report API + Documentation + Acceptance Gates

**Purpose:** Aggregate report endpoint, final docs, and full-suite acceptance run.

**Files to create/modify:**
```
app/api/v1/endpoints/report.py          ← GET /v1/encounters/{encounter_id}/report
app/api/v1/router.py                    ← register all endpoints
docs/architecture.md
docs/dual-rag-design.md
docs/tech-stack.md
tests/api/test_encounter_report.py
```

**Report response shape:**
```json
{
  "encounter_id": "...",
  "request_id": "...",
  "emr": { "soap_json": {}, "note_text": "", "is_final": false },
  "icd_suggestions": [{ "code": "", "rank": 1, "confidence": 0.9, "rationale": "", "evidence": [] }],
  "cpt_suggestions": [{ "code": "", "rank": 1, "confidence": 0.9, "rationale": "", "evidence": [] }],
  "conflict_flags": [],
  "generated_at": "..."
}
```

**Steps:**
- [ ] Step 1: Write failing E2E test for `GET /v1/encounters/{encounter_id}/report` using a fixture that runs the full generate pipeline.
- [ ] Step 2: Implement `report.py` endpoint: query `EmrNote` (current version), `CodingSuggestion` + `CodingEvidenceLink`, assemble response.
- [ ] Step 3: Register all endpoints in `router.py`.
- [ ] Step 4: Write `docs/architecture.md`, `docs/dual-rag-design.md`, `docs/tech-stack.md`.
- [ ] Step 5: Run full test suite. All tests must pass.
- [ ] Step 6: Run `alembic upgrade head` on a clean DB. Confirm idempotent.
- [ ] Step 7: Verify all acceptance criteria below.
- [ ] Step 8: Commit.

---

## Acceptance Criteria

| # | Criterion | Target |
|---|-----------|--------|
| 1 | EMR schema pass rate on internal test fixtures | >= 95% |
| 2 | Coding outputs include evidence refs | 100% of responses |
| 3 | All ICD/CPT outputs default to `needs_review` | 100% |
| 4 | P95 response latency (warm, single concurrent request, <= 500 patient chunks) | <= 6s |
| 5 | Every response traceable by `request_id` across `llm_calls` and `retrieval_logs` | 100% |
| 6 | Full SSN appears in default API responses | 0 occurrences |
| 7 | SSN access audit event coverage for privileged endpoints | 100% |
| 8 | Sensitive fields redaction tests pass with zero leakage | 0 leaks |
| 9 | English-only EMR output compliance for MVP endpoints | 100% |
| 10 | Guideline retrieval scoped to respiratory documents for MVP | 100% |
| 11 | Embedding dimension confirmed via live API call before migration 001 | Gate cleared |
| 12 | Docker Compose uses `pgvector/pgvector:pg17` image | Verified |

---

## Risk Controls

| Risk | Control |
|------|---------|
| Hardcoded credentials | No API keys or secrets in source files; all from env vars; CI lint check for `sk-` patterns |
| PII in logs | `encryption_service.py` encrypts before persist; log redaction middleware strips sensitive fields |
| LLM coding errors | Deterministic `rule_engine.py` always post-checks; invalid codes rejected before persist |
| LLM/retrieval failures | `fail_safe_node` in LangGraph returns partial response with `error` flag |
| Full SSN exposure | Default APIs return `ssn_last4` only; full decrypt requires privileged role + audit reason |
| Encryption key loss | Document key rotation procedure in `docs/architecture.md` before first deploy |
| Audit log tampering | Application role has INSERT-only on `audit_events`; no UPDATE/DELETE permitted |
| Embedding dimension drift | `EMBEDDING_DIM` constant in config; migration hardcodes value; changing it requires explicit migration |
| CPT data quality | 全量 CSV 含 3,801 deleted 码和 5 条非标准本地扩展码；ingestion 层清洗，不入库 |
