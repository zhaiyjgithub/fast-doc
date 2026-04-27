# Recording EMR: Provider Context + Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or execute tasks inline in this session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the extension recording page, add optional provider “Context” text (shadcn Tabs: Context | Transcript, default Transcript) before EMR generate, and pass that text through `POST /v1/emr/generate` into `EMRService` so the LLM user prompt includes a redacted provider-supplied section.

**Architecture:** Optional `provider_context` on the async EMR request body; `EMRService.generate` prepends `## Provider-supplied context` to the existing user message when non-empty. Extension: `GenerateEmrPayload.providerContext` → JSON `provider_context`; `RecordingPage` holds local state and extends `onGenerateEMR` with an optional fourth argument.

**Tech stack:** FastAPI + Pydantic (fast-doc), React + WXT + shadcn Tabs (fast-doc-extension), pytest.

---

## File map

| Area | File | Role |
|------|------|------|
| Backend API | `fast-doc/app/api/v1/endpoints/emr.py` | `EMRGenerateRequest.provider_context`, pass to `svc.generate` |
| Backend service | `fast-doc/app/services/emr_service.py` | `generate(..., provider_context=None)`, inject into LLM user message |
| Extension API | `fast-doc-extension/lib/emr-api.ts` | `GenerateEmrPayload`, JSON body |
| Extension UI | `fast-doc-extension/pages/recording-page.tsx` | Tabs + state + callback signature |
| Extension app | `fast-doc-extension/entrypoints/sidepanel/App.tsx` | `handleGenerateEMR` passes through to `generateEmr` |
| Tests | `fast-doc/tests/api/test_emr_endpoint.py` | Accept optional field (smoke) |
| Tests | `fast-doc/tests/services/test_emr_service.py` | Assert LLM receives provider section when set |

---

### Task 1: Backend — request schema and background handoff

**Files:**
- Modify: `fast-doc/app/api/v1/endpoints/emr.py` (class `EMRGenerateRequest`, `_run_emr_background`)

- [ ] **Step 1:** Add optional field to `EMRGenerateRequest`:

```python
provider_context: str | None = Field(default=None, max_length=16_000)
```

(Use a reasonable max length; adjust if project standard differs.)

- [ ] **Step 2:** In `_run_emr_background`, pass `provider_context=body.provider_context` into `svc.generate(...)`.

- [ ] **Step 3:** Run backend tests for EMR:

```bash
cd /Users/yuanji/Desktop/project/fast-doc && pytest tests/api/test_emr_endpoint.py tests/services/test_emr_service.py -q
```

Expected: PASS (Task 2 test not added yet — may still PASS).

- [ ] **Step 4:** Commit (optional per repo policy):

```bash
git add app/api/v1/endpoints/emr.py && git commit -m "feat(emr): accept optional provider_context on generate request"
```

---

### Task 2: Backend — EMRService prompt injection

**Files:**
- Modify: `fast-doc/app/services/emr_service.py` (`generate` signature and user message block)

- [ ] **Step 1:** Add parameter `provider_context: str | None = None` to `async def generate(` after `source`.

- [ ] **Step 2:** Before building `user_message`, compute:

```python
ctx = (provider_context or "").strip()
redacted_provider = redact_phi(ctx) if ctx else ""
```

- [ ] **Step 3:** Build `user_message`:

If `redacted_provider` is non-empty, prefix:

`f"## Provider-supplied context\n{redacted_provider}\n\n"`

then keep existing `## Encounter Transcript`, `## Clinical Context`, and closing instruction unchanged.

- [ ] **Step 4:** Optionally add to `context_trace_json` on `EmrNote` a flag or length, e.g. `"provider_context_chars": len(redacted_provider)` when non-empty (YAGNI: skip if not needed for debugging).

- [ ] **Step 5:** Run pytest including new test from Task 3.

---

### Task 3: Backend — unit test for provider context in LLM call

**Files:**
- Modify: `fast-doc/tests/services/test_emr_service.py`

- [ ] **Step 1:** Add `async def test_emr_generate_includes_provider_context_in_user_message(db_session):` that reuses the same patch pattern as `test_emr_generate_with_mocked_llm` (minimal: patch RAG + `llm_adapter.chat`), call `svc.generate(..., provider_context="BP 140/90, HR 88")`, then `llm_adapter.chat.assert_awaited()` and inspect first call `kwargs` or `call_args` for `messages[1]["content"]` containing `## Provider-supplied context` and `140/90` (or redacted form if redact_phi changes digits — assert section header + substring that survives redaction; use alphabetic context like "Prior MI in 2020" if PHI redaction strips numbers).

**Recommendation:** Use `provider_context="Follow-up visit for hypertension management."` and assert that substring appears in user content.

- [ ] **Step 2:** Run:

```bash
cd /Users/yuanji/Desktop/project/fast-doc && pytest tests/services/test_emr_service.py::test_emr_generate_includes_provider_context_in_user_message -q
```

Expected: PASS.

---

### Task 4: Extension — API payload and POST body

**Files:**
- Modify: `fast-doc-extension/lib/emr-api.ts`

- [ ] **Step 1:** Extend `GenerateEmrPayload`:

```typescript
providerContext?: string | null
```

- [ ] **Step 2:** In `generateEmr`, include in `JSON.stringify`:

```typescript
provider_context: payload.providerContext?.trim() || undefined,
```

Omit key when empty.

- [ ] **Step 3:** If extension has `npm run build` or `pnpm check`, run it from `fast-doc-extension`.

---

### Task 5: Extension — RecordingPage tabs and callback

**Files:**
- Modify: `fast-doc-extension/pages/recording-page.tsx`

- [ ] **Step 1:** Import `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` from `@/components/ui/tabs`.

- [ ] **Step 2:** Extend `RecordingPageProps.onGenerateEMR` to optional 4th argument: `providerContext?: string`.

- [ ] **Step 3:** State: `const [emrContext, setEmrContext] = React.useState('')`.

- [ ] **Step 4:** Reset `emrContext` when: manual flow Cancel (with transcript reset); `beginNewRecordingFromClick` when clearing session (same places as transcript reset for a fresh visit).

- [ ] **Step 5:** For `state === 'ready' && showManualInput` and for `state === 'processing'` with transcript editor: wrap transcript + new textarea in:

```tsx
<Tabs defaultValue="transcript" className="w-full">
  <TabsList className="grid w-full grid-cols-2">
    <TabsTrigger value="context">Context</TabsTrigger>
    <TabsTrigger value="transcript">Transcript</TabsTrigger>
  </TabsList>
  <TabsContent value="context" className="mt-3">
    <Textarea ... value={emrContext} onChange=... placeholder explaining optional provider notes />
  </TabsContent>
  <TabsContent value="transcript" className="mt-3">
    ... existing transcript Textarea ...
  </TabsContent>
</Tabs>
```

- [ ] **Step 6:** `onGenerateEMR(transcript, elapsedTime, 'paste'|'voice', emrContext.trim() || undefined)`.

---

### Task 6: Extension — App handleGenerateEMR

**Files:**
- Modify: `fast-doc-extension/entrypoints/sidepanel/App.tsx`

- [ ] **Step 1:** Extend `handleGenerateEMR` signature with optional `providerContext?: string`.

- [ ] **Step 2:** Pass `providerContext` into `generateEmr(..., { ..., providerContext })`.

- [ ] **Step 3:** Verify dependency array of `useCallback` includes any new stable refs (usually unchanged).

---

### Task 7: API contract test (optional smoke)

**Files:**
- Modify: `fast-doc/tests/api/test_emr_endpoint.py`

- [ ] **Step 1:** Duplicate `test_emr_generate_success` request JSON with `"provider_context": "Stable angina, on aspirin."` — assert still 202 and same mocked behavior.

---

## Spec coverage (self-review)

| Requirement | Task |
|-------------|------|
| Context input for provider | Task 5 |
| Tab bar, Context left, Transcript default | Task 5 (`TabsList` order, `defaultValue="transcript"`) |
| shadcn/ui Tabs | Task 5 (existing `@/components/ui/tabs`) |
| Data reaches EMR generation | Tasks 1–2, 4–6 |
| PHI handling | Task 2 (`redact_phi` on provider text) |

## Placeholder scan

None — all steps name concrete files and behaviors.

## Type consistency

- JSON: `provider_context` (snake_case)
- TypeScript payload: `providerContext` (camelCase)
- Python: `provider_context`

---

**Plan complete.** Execution: subagent-driven-development (adapted: implement tasks in session if implementer Task type unavailable; final `code-reviewer` subagent after all tasks).

---

## Execution log (2026-04-27)

- [x] Tasks 1–7 implemented in-session (no separate implementer Task type in environment).
- [x] `uv run pytest tests/api/test_emr_endpoint.py tests/services/test_emr_service.py` — 16 passed.
- [x] Extension `npm run compile` — passed.
- [x] Final **code-reviewer** subagent: **Ready to merge**; optional follow-ups: client-side 16k alignment with API, and whether RAG should incorporate `provider_context`.
