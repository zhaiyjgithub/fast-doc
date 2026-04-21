# Extension Encounter/Report Integration Design

## Goal

Integrate the extension with backend Encounter + Report APIs end-to-end:
- match patient via parse-demographics
- record transcript
- create encounter (if new) then generate EMR
- render SOAP + ICD/CPT from report
- show today's encounters on Home
- show paginated encounters on Notes
- open encounter from Home/Notes into AI EMR detail
- add Transcript entry in AI EMR FAB and show a read-only transcript page

## Scope

### In-scope

1. Frontend data flow integration in `fast-doc-extension`:
   - New encounter/report API client
   - App-level state for active encounter + report + transcript
   - Home/Notes data load from encounter APIs
   - SOAP page display driven by report payload (not static mocks)
   - Transcript page + FAB entry

2. Backend support in `fast-doc` required by frontend workflow:
   - Provide paginated all-encounter list endpoint for Home/Notes usage
   - Include transcript text in encounter detail/list payload for transcript page
   - Ensure EMR generation path updates encounter transcript/status consistently

3. Documentation updates for new frontend integration contract.

### Out-of-scope

- Full redesign of existing UI visual style
- Replacing all mock patients in search sheet with backend patient search
- Real-time websocket updates (polling/request-response only)

## Functional Requirements

1. **Match patient**
   - Tap match patient still calls parse-demographics.
   - Parsed patient returned from backend remains source of truth.

2. **Generate flow**
   - User records transcript in Recording page.
   - On AI Generate:
     - if no active encounter: create encounter first
     - then call EMR generate API
     - then fetch report and render in AI EMR page

3. **AI EMR display**
   - SOAP sections sourced from report `emr.soap_note`.
   - ICD/CPT cards sourced from report `icd_suggestions` and `cpt_suggestions`.

4. **Home page list**
   - Load today's encounters via encounter list API.
   - Clicking an encounter opens AI EMR for that encounter and loads latest report.

5. **Notes page list**
   - Paginated encounter list via encounter list API.
   - Supports pagination controls and opening encounter detail.

6. **Transcript entry**
   - Add `Transcript` action in AI EMR FAB.
   - Open transcript page:
     - header shows patient info
     - body shows read-only transcript dialogue/content

## API/Data Contract Decisions

### Backend additions

1. Add `GET /v1/encounters` with pagination and optional today filter:
   - query: `page`, `page_size`, `today_only`
   - response: `EncounterOut[]`

2. Extend `EncounterOut` with:
   - `transcript_text: str | None`

3. During EMR generation:
   - persist transcript onto encounter (`transcript_text`)
   - update encounter status to reflect generation completion

### Frontend internal model

Define extension-side encounter/report models aligned with backend fields:
- `EncounterSummary` mirrors `EncounterOut`
- `EncounterReport` mirrors `/encounters/{id}/report`
- `ReportCodeSuggestion` mirrors backend `code_type/rank/condition/description/confidence/rationale/status/evidence`

## Edge Cases

- Generate clicked with patient that is not backend UUID-backed: show actionable toast and stop.
- Report fetch returns `404`: show empty-state + retry.
- Transcript unavailable: transcript page shows explicit no-transcript message.
- Encounter list errors: keep UI usable with retry CTA.

## Testing Requirements

### Backend

1. `GET /encounters` returns paginated list.
2. `today_only=true` filters to current date.
3. Encounter payload includes `transcript_text`.
4. EMR generation updates encounter transcript and status.

### Frontend

1. Generate flow:
   - create encounter when no active encounter
   - call EMR generate
   - fetch report and render SOAP/code data
2. Home/Notes load encounter list API.
3. Clicking encounter opens AI EMR populated from report.
4. Transcript FAB entry navigates to transcript page and renders read-only content.
