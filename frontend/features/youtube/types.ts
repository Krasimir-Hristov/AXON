export interface VideoTranscriptOut {
  id: string;
  youtube_url: string;
  video_id: string;
  title: string | null;
  channel: string | null;
  duration_s: number | null;
  summary: string;
  key_points: string[];
  created_at: string;
}
