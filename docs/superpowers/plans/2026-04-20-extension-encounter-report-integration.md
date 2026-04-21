# Extension Encounter/Report Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate extension recording-to-EMR flow with encounter/report APIs, including encounter list views and transcript detail navigation.

**Architecture:** Add minimal backend support for encounter listing/transcript exposure, then build typed frontend API client and App-level orchestration that drives Home/Notes/AI-EMR from backend data. Keep UI components mostly intact by replacing local mock sources with report/encounter models.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, React + TypeScript (WXT), fetch API

---

### Task 1: Backend encounter list/transcript contract

**Files:**
- Modify: `app/api/v1/endpoints/encounters.py`
- Test: `tests/api/test_encounter_list_endpoint.py` (create)

- [ ] **Step 1: Write failing endpoint tests**
```python
async def test_list_encounters_returns_paginated_items(async_client, fake_db): ...
async def test_list_encounters_today_only_filters_by_date(async_client, fake_db): ...
```

- [ ] **Step 2: Run tests to verify failure**
Run: `uv run pytest tests/api/test_encounter_list_endpoint.py -q`
Expected: FAIL (endpoint/shape missing)

- [ ] **Step 3: Implement list endpoint + transcript field**
```python
class EncounterOut(BaseModel):
    ...
    transcript_text: str | None = None

@router.get("/encounters", response_model=list[EncounterOut])
async def list_encounters(..., today_only: bool = Query(False)):
    ...
```

- [ ] **Step 4: Run tests to verify pass**
Run: `uv run pytest tests/api/test_encounter_list_endpoint.py -q`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/api/v1/endpoints/encounters.py tests/api/test_encounter_list_endpoint.py
git commit -m "feat(encounter): add paginated encounter list with transcript field"
```

### Task 2: Backend EMR generate updates encounter transcript/status

**Files:**
- Modify: `app/services/emr_service.py`
- Test: `tests/services/test_emr_service.py`

- [ ] **Step 1: Write failing service test for transcript/status update**
```python
async def test_generate_updates_encounter_transcript_and_status(db_session): ...
```

- [ ] **Step 2: Run targeted test to confirm fail**
Run: `uv run pytest tests/services/test_emr_service.py -q`
Expected: FAIL on missing update behavior

- [ ] **Step 3: Implement update logic inside generate path**
```python
encounter.transcript_text = transcript
encounter.status = "completed"
await self.db.flush()
```

- [ ] **Step 4: Re-run service tests**
Run: `uv run pytest tests/services/test_emr_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add app/services/emr_service.py tests/services/test_emr_service.py
git commit -m "feat(emr): persist encounter transcript and completion status"
```

### Task 3: Extension API clients for encounter/report/emr

**Files:**
- Create: `fast-doc-extension/lib/encounter-api.ts`
- Create: `fast-doc-extension/lib/report-api.ts`
- Create: `fast-doc-extension/lib/emr-api.ts`
- Test/verify: compile

- [ ] **Step 1: Add typed request/response mappers**
```ts
export type EncounterSummary = { ... }
export type EncounterReport = { ... }
```

- [ ] **Step 2: Implement API methods**
```ts
createEncounter(...)
listEncounters(...)
getEncounter(...)
getEncounterReport(...)
generateEmr(...)
```

- [ ] **Step 3: Compile check**
Run: `npm run compile`
Expected: PASS

- [ ] **Step 4: Commit**
```bash
git add fast-doc-extension/lib/encounter-api.ts fast-doc-extension/lib/report-api.ts fast-doc-extension/lib/emr-api.ts
git commit -m "feat(extension): add typed encounter report emr API clients"
```

### Task 4: App orchestration for generate/report + Home/Notes API data

**Files:**
- Modify: `fast-doc-extension/entrypoints/sidepanel/App.tsx`
- Modify: `fast-doc-extension/pages/home-page.tsx`
- Modify: `fast-doc-extension/pages/notes-page.tsx`

- [ ] **Step 1: Wire generate flow**
```ts
if (!activeEncounterId) createEncounter(...)
await generateEmr(...)
const report = await getEncounterReport(...)
```

- [ ] **Step 2: Load lists from encounter API**
```ts
home: listEncounters({ todayOnly: true })
notes: listEncounters({ page, pageSize })
```

- [ ] **Step 3: Encounter click opens SOAP with latest report**
```ts
setActiveEncounterId(id)
setCurrentPage('soap')
await loadReport(id)
```

- [ ] **Step 4: Compile check**
Run: `npm run compile`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add fast-doc-extension/entrypoints/sidepanel/App.tsx fast-doc-extension/pages/home-page.tsx fast-doc-extension/pages/notes-page.tsx
git commit -m "feat(extension): drive home notes and generate flow from encounter APIs"
```

### Task 5: SOAP page report rendering + Transcript page/FAB entry

**Files:**
- Modify: `fast-doc-extension/pages/soap-page.tsx`
- Create: `fast-doc-extension/pages/transcript-page.tsx`
- Modify: `fast-doc-extension/entrypoints/sidepanel/App.tsx`

- [ ] **Step 1: Adapt SOAP props to backend report model**
```ts
type SoapPageProps = { report: EncounterReport | null; ... }
```

- [ ] **Step 2: Add FAB Transcript action**
```ts
{ icon: MessageSquareText, label: 'Transcript', action: 'transcript' }
```

- [ ] **Step 3: Build transcript view-only page**
```tsx
<TranscriptPage patient={patient} transcript={encounter?.transcriptText} />
```

- [ ] **Step 4: Compile check**
Run: `npm run compile`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add fast-doc-extension/pages/soap-page.tsx fast-doc-extension/pages/transcript-page.tsx fast-doc-extension/entrypoints/sidepanel/App.tsx
git commit -m "feat(extension): add transcript page and report-driven soap detail"
```

### Task 6: Docs and final verification

**Files:**
- Modify: `docs/frontend-encounter-report-api-guide.md`
- Modify: `docs/api-integration-guide.md`

- [ ] **Step 1: Update docs for encounter list/transcript usage and frontend flow**
- [ ] **Step 2: Run backend tests**
Run: `uv run pytest tests/api/test_encounter_list_endpoint.py tests/services/test_emr_service.py tests/api/test_encounter_report_duration.py -q`
Expected: PASS
- [ ] **Step 3: Run extension compile**
Run: `npm run compile` (in `fast-doc-extension`)
Expected: PASS
- [ ] **Step 4: Run lint diagnostics on touched files**
- [ ] **Step 5: Commit**
```bash
git add docs/frontend-encounter-report-api-guide.md docs/api-integration-guide.md
git commit -m "docs(api): document encounter list report transcript frontend integration"
```
