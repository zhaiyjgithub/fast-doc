# EMR Note Conversation Duration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist conversation duration seconds for each EMR generation into `emr_notes` and expose it through the encounter report.

**Architecture:** Extend request payloads to accept optional duration, thread the value through endpoint and service layers, persist in `EmrNote`, then return it in report response. Keep this backward compatible by using nullable fields and optional request params.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async ORM, Alembic, Pytest

---

### Task 1: Database + ORM support for duration

**Files:**
- Create: `alembic/versions/015_emr_note_conversation_duration.py`
- Modify: `app/models/clinical.py`
- Test: `tests/api/test_emr_endpoint.py` (indirect runtime coverage) 

- [ ] **Step 1: Add migration for nullable duration column**

```python
# alembic/versions/015_emr_note_conversation_duration.py
op.add_column(
    "emr_notes",
    sa.Column("conversation_duration_seconds", sa.Integer(), nullable=True),
)
```

- [ ] **Step 2: Add downgrade for column removal**

```python
op.drop_column("emr_notes", "conversation_duration_seconds")
```

- [ ] **Step 3: Update SQLAlchemy model**

```python
conversation_duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
```

- [ ] **Step 4: Run targeted tests**

Run: `uv run pytest tests/api/test_emr_endpoint.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/015_emr_note_conversation_duration.py app/models/clinical.py
git commit -m "Add conversation duration column to emr_notes"
```

### Task 2: Accept and persist duration in generation flows

**Files:**
- Modify: `app/api/v1/endpoints/emr.py`
- Modify: `app/api/v1/endpoints/encounters.py`
- Modify: `app/services/emr_service.py`
- Test: `tests/api/test_emr_endpoint.py`
- Test: `tests/api/test_encounter_transcript_duration.py` (new)

- [ ] **Step 1: Add optional duration to request schemas**

```python
conversation_duration_seconds: int | None = Field(default=None, ge=0)
```

- [ ] **Step 2: Thread duration through endpoint -> service call**

```python
state = await svc.generate(
    ...,
    conversation_duration_seconds=body.conversation_duration_seconds,
)
```

- [ ] **Step 3: Extend transcript background helper signature**

```python
async def _background_generate_emr(..., conversation_duration_seconds: int | None = None) -> None:
    ...
    await svc.generate(..., conversation_duration_seconds=conversation_duration_seconds)
```

- [ ] **Step 4: Pass transcript payload duration to background task**

```python
asyncio.create_task(
    _background_generate_emr(
        ...,
        conversation_duration_seconds=body.conversation_duration_seconds,
    )
)
```

- [ ] **Step 5: Persist duration when creating EmrNote**

```python
emr_note = EmrNote(
    ...,
    conversation_duration_seconds=conversation_duration_seconds,
)
```

- [ ] **Step 6: Add/adjust endpoint tests**

```python
# tests/api/test_emr_endpoint.py
assert generate_mock.await_args.kwargs["conversation_duration_seconds"] == 185
```

```python
# tests/api/test_encounter_transcript_duration.py
assert bg_mock.await_args.kwargs["conversation_duration_seconds"] == 185
```

- [ ] **Step 7: Run targeted API tests**

Run: `uv run pytest tests/api/test_emr_endpoint.py tests/api/test_encounter_transcript_duration.py -q`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/api/v1/endpoints/emr.py app/api/v1/endpoints/encounters.py app/services/emr_service.py tests/api/test_emr_endpoint.py tests/api/test_encounter_transcript_duration.py
git commit -m "Persist conversation duration in EMR generation flows"
```

### Task 3: Expose duration in report response + docs

**Files:**
- Modify: `app/api/v1/endpoints/report.py`
- Modify: `docs/api-integration-guide.md`
- Test: `tests/api/test_encounter_report_duration.py` (new)

- [ ] **Step 1: Add duration field to report EMR schema**

```python
class EMRSummary(BaseModel):
    ...
    conversation_duration_seconds: int | None = None
```

- [ ] **Step 2: Map field from latest note**

```python
conversation_duration_seconds=note.conversation_duration_seconds,
```

- [ ] **Step 3: Add report API test for duration field**

```python
assert body["emr"]["conversation_duration_seconds"] == 185
```

- [ ] **Step 4: Update integration guide**

```markdown
- conversation_duration_seconds (optional, >=0) on EMR generate/transcript APIs
- emr.conversation_duration_seconds in encounter report response
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/api/test_emr_endpoint.py tests/api/test_encounter_transcript_duration.py tests/api/test_encounter_report_duration.py -q`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/endpoints/report.py docs/api-integration-guide.md tests/api/test_encounter_report_duration.py
git commit -m "Expose conversation duration in encounter report and docs"
```

### Task 4: Final verification

**Files:**
- Modify: none
- Test: `tests/api/test_emr_endpoint.py`
- Test: `tests/api/test_encounter_transcript_duration.py`
- Test: `tests/api/test_encounter_report_duration.py`

- [ ] **Step 1: Run final focused suite**

Run: `uv run pytest tests/api/test_emr_endpoint.py tests/api/test_encounter_transcript_duration.py tests/api/test_encounter_report_duration.py`  
Expected: all PASS

- [ ] **Step 2: Run lint diagnostics for touched files**

Run IDE lint check for:
- `app/api/v1/endpoints/emr.py`
- `app/api/v1/endpoints/encounters.py`
- `app/api/v1/endpoints/report.py`
- `app/services/emr_service.py`
- `app/models/clinical.py`

- [ ] **Step 3: Confirm no unintended changes**

Run: `git status --short`  
Expected: only planned files changed/committed.
