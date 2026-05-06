/**
 * Memory feature types — mirror the backend Pydantic schemas in
 * `backend/app/features/memory/schemas.py`. UUID and datetime fields arrive
 * as ISO strings over HTTP, so they are typed as `string` here.
 */

export interface MemoryEntry {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface MemorySearchResult extends MemoryEntry {
  similarity: number;
}

export interface MemoryCreatePayload {
  content: string;
  metadata?: Record<string, unknown>;
}

export interface MemorySearchPayload {
  query: string;
  limit?: number;
  threshold?: number;
}

export interface FileUploadResult {
  file_name: string;
  chunks_created: number;
  memory_ids: string[];
}
