# Knowledge Base Assisted Writing Design

## Summary

Add a user-uploaded knowledge base so the system can read internal files and use them during article creation. Version 1 supports Markdown, TXT, and PDF files. The knowledge base stays independent from the existing material library, but the article workshop can recommend across all three sources:

- knowledge base chunks for internal facts, opinions, product knowledge, and domain context
- `fact_material` benchmarks for traceable external facts and cases
- `reference_article` benchmarks for viral article structure and writing style

The goal is to let a user choose a topic and a hotspot, then have the AI agent automatically pick suitable knowledge snippets and a matching viral reference article before generating a compliant draft.

## Goals

- Let users upload Markdown, TXT, and PDF knowledge files from the web UI.
- Parse files into searchable text chunks and store them in SQLite.
- Let article generation use automatic knowledge recommendations by default.
- Let advanced users limit recommendations to selected knowledge files.
- Keep deployment simple on Mac and Windows.
- Avoid introducing a vector database in v1.
- Preserve the current material library and publishing flow.

## Non-Goals

- No complex permissions or multi-tenant knowledge isolation in v1.
- No full vector search service in v1.
- No automatic publishing. The existing manual publish confirmation remains.
- No Word document support in v1.
- No guarantee that uploaded knowledge is factually correct. The UI should frame it as user-provided context.

## User Experience

### Knowledge Library Area

Add a Knowledge Base section under the existing material library page. It should support:

- Upload one or more `.md`, `.txt`, or `.pdf` files.
- Show file name, file type, chunk count, parse status, upload time, and optional error.
- Delete a knowledge file and its chunks.
- Make it clear that uploaded files are used as internal knowledge, not viral writing references.

PDF parsing failures should not break the whole page. If PDF support is unavailable in the environment, Markdown and TXT should still work, and settings diagnostics can guide users to install the optional PDF dependency.

### Article Workshop

Extend the article workshop with:

- optional hotspot selector or selected hotspot context
- optional knowledge file scope selector
- button: "Smart Recommend Materials"
- recommendation result sections:
  - knowledge snippets
  - fact materials
  - viral reference article
  - reasons for each selection

The default behavior should be low-friction: if the user enters a topic and does not choose a scope, the system searches all active knowledge files and existing materials.

### Hotspot Flow

When a user opens a hotspot creative brief, the system can include recommended knowledge chunks in addition to selected fact materials and a viral reference article. The hotspot remains the trend hook; the knowledge base supplies domain substance.

## Data Model

Add `knowledge_files`:

- `id`
- `filename`
- `original_filename`
- `file_type`
- `file_path`
- `status`: `ready`, `processing`, `failed`
- `chunk_count`
- `error_message`
- `created_at`
- `updated_at`

Add `knowledge_chunks`:

- `id`
- `file_id`
- `chunk_index`
- `title`
- `content`
- `content_hash`
- `keywords_json`
- `created_at`

Extend `Topic` only if needed for persistence:

- `knowledge_chunk_ids_json`

Do not merge knowledge chunks into `benchmarks`. A chunk is a factual/contextual source, while a benchmark keeps its current role as either fact material or viral reference.

## Backend Interfaces

Add:

- `POST /api/knowledge/files`
  - multipart upload
  - accepts `.md`, `.txt`, `.pdf`
  - parses immediately in v1
  - returns file metadata and chunk count

- `GET /api/knowledge/files`
  - returns file list with status and chunk count

- `DELETE /api/knowledge/files/<id>`
  - deletes metadata, chunks, and uploaded file

- `POST /api/knowledge/recommend`
  - request: `topic`, optional `hotspot_title`, optional `knowledge_file_ids`, optional `limit`
  - returns ranked knowledge chunks, fact materials, reference articles, and selection reasons

Extend:

- `POST /api/articles/generate`
  - accepts `knowledge_chunk_ids`
  - generation prompt includes selected chunks as user knowledge context

- `POST /api/topics/<id>/brief`
  - accepts `knowledge_chunk_ids`
  - creative brief includes relevant knowledge snippets

- `POST /api/topics/<id>/generate`
  - uses saved knowledge chunk IDs from the topic brief

## Recommendation Logic

Use a two-stage v1 recommendation pipeline:

1. Local retrieval:
   - tokenize topic, hotspot title, and keyword fields
   - score knowledge chunks by title/content keyword overlap
   - score fact materials and reference articles using the existing benchmark recommendation logic

2. AI selection:
   - give the top local candidates to the configured AI model
   - ask it to choose:
     - up to 5 knowledge chunks
     - up to 3 fact materials
     - 1 viral reference article
   - require structured JSON with IDs and reasons

If the AI returns invalid JSON, fall back to local ranking so the workflow still works.

## Prompt Contract

Generation should make source roles explicit:

- Knowledge chunks: use as internal facts, business context, examples, and user-owned viewpoints.
- Fact materials: use for external facts and traceable claims.
- Viral reference article: use for structure, rhythm, and expression style only.
- Hotspot: use as the timely hook, not as the sole substance of the article.

The prompt should discourage unsupported factual claims and ask the model to cite source titles in planning notes where helpful.

## File Parsing

Markdown and TXT:

- read as UTF-8 with error replacement
- strip excessive whitespace
- preserve headings as chunk titles when possible

PDF:

- use a lightweight Python parser such as `pypdf` if installed
- if unavailable, return a clear error saying PDF parsing dependency is missing
- settings diagnostics can surface this optional dependency

Chunking:

- target 800-1200 Chinese characters or roughly comparable text length
- avoid splitting in the middle of headings when possible
- compute `content_hash` for deduplication

## Frontend Changes

Add `frontend/src/api/knowledge.ts`.

Update `BenchmarksPage.tsx`:

- add a Knowledge Base section above or below candidate material review
- upload control for md/txt/pdf
- list uploaded files and parse status
- delete action

Update `WorkshopPage.tsx`:

- optional hotspot selector
- optional knowledge file selector
- "Smart Recommend Materials" action calls `/api/knowledge/recommend`
- display recommendation reasons
- allow user to adjust selected knowledge chunks, fact materials, and viral reference before generation

Update `TopicsPage.tsx`:

- creative brief modal can include recommended knowledge chunks
- brief generation submits selected knowledge chunk IDs

## Error Handling

- Unsupported file type: return 400 with allowed extensions.
- Oversized file: return 400 with max size guidance.
- PDF parser missing: mark file failed with a clear dependency message.
- Empty parsed text: mark file failed and show "No usable text was parsed".
- Duplicate chunk hash: skip duplicate chunk.
- AI rerank failure: use local ranking and show a non-blocking warning.

## Testing

Backend tests:

- upload Markdown creates `knowledge_files` and chunks
- upload TXT creates chunks
- unsupported extension returns 400
- duplicate chunks are skipped
- recommendation returns knowledge chunks plus benchmark recommendations
- AI invalid JSON falls back to local ranking
- article generation receives selected knowledge chunk context
- old SQLite database creates new tables during `init_db()`

Frontend verification:

- knowledge upload UI accepts md/txt/pdf
- uploaded file appears with chunk count
- delete removes the file from the list
- workshop recommendation shows knowledge snippets, fact materials, and viral reference article
- generation still works without knowledge files

Regression:

- existing manual material creation still works
- existing candidate approval still works
- existing topic brief and article generation still work without knowledge chunks
- frontend lint and build pass

## Deployment Notes

No new service is required. SQLite remains the only database. PDF parsing is optional but recommended. If the dependency is missing, Markdown and TXT workflows continue to work.

The setup wizard or diagnostics should mention the optional PDF parser so non-technical users understand why PDF upload may fail in a fresh environment.
