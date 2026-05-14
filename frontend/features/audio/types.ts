export interface AudioEntryOut {
  id: string;
  filename: string;
  title: string;
  source_type: string;
  source_id: string | null;
  duration_s: number | null;
  created_at: string;
  signed_url: string;
}
