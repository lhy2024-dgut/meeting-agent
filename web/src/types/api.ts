export type MeetingSummary = {
  id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  duration_category: string;
  duration_label: string;
  environment: string;
  environment_label: string;
  short_summary: string;
  project_name: string;
  action_item_count: number;
  resolution_count: number;
};

export type MeetingListResponse = {
  items: MeetingSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type MeetingMutationResponse = {
  success: boolean;
};

export type AuthTokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type CurrentUser = {
  id: number;
  username: string;
  email: string;
  display_name: string;
  created_at: string | null;
  last_login_at: string | null;
};

export type TodoItem = {
  id: number;
  user_id: number;
  meeting_id: number;
  content: string;
  assignee: string | null;
  due_date: string | null;
  status: "pending" | "done" | "cancelled";
  priority: "high" | "medium" | "low";
  created_at: string | null;
  updated_at: string | null;
};

export type TodoStatusLog = {
  id: number;
  todo_id: number;
  from_status: string | null;
  to_status: string;
  changed_by: string;
  changed_at: string | null;
  reason: string | null;
};

export type TodoListResponse = {
  items: TodoItem[];
};

export type TodoStatusLogsResponse = {
  items: TodoStatusLog[];
};

export type MeetingTermsResponse = {
  meeting_id: number;
  terms: string[];
};

export type MeetingDetail = {
  id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  date_text: string;
  duration_category: string;
  duration_label: string;
  environment: string;
  environment_label: string;
  duration_seconds: number;
  duration_display: string;
  minutes_text: string;
  action_items_text: string;
  resolutions_text: string;
  short_summary: string;
  project_name: string;
  action_item_count: number;
  resolution_count: number;
  transcript_count: number;
  todos: TodoItem[];
};

export type TranscriptSegment = {
  id: number;
  text: string;
  timestamp: number;
  start_time: number;
  end_time: number;
};

export type TranscriptResponse = {
  meeting_id: number;
  updated_at: string;
  full_text: string;
  segments: TranscriptSegment[];
};

export type DistributionItem = {
  key: string;
  label: string;
  count: number;
};

export type TrendItem = {
  month: string;
  count: number;
};

export type StatsOverviewResponse = {
  total_meetings: number;
  short_meetings: number;
  medium_meetings: number;
  long_meetings: number;
  multi_speaker_meetings: number;
  duration_distribution: DistributionItem[];
  environment_distribution: DistributionItem[];
  monthly_trend: TrendItem[];
};

export type SceneOption = {
  scene: string;
  display_name: string;
  description: string;
};

export type TemplateOption = {
  name: string;
  label: string;
  has_docx: boolean;
  has_pdf: boolean;
  preview_path: string | null;
};

export type UploadMetadataResponse = {
  scenes: SceneOption[];
  templates: TemplateOption[];
  output_formats: string[];
  asr_models: string[];
  chunk_strategies: Array<{
    value: string;
    label: string;
  }>;
  transcription_modes: Array<{
    value: string;
    label: string;
  }>;
};

export type CreateJobResponse = {
  job_id: string;
  status: string;
};

export type JobStatusResponse = {
  job_id: string;
  job_type: string;
  status: string;
  progress_pct: number;
  stage: string;
  message: string;
  created_at: string;
  updated_at: string;
  result: {
    meeting_id: number | null;
    title: string | null;
    output_path: string | null;
  } | null;
  error: string | null;
};

export type HtmlSummaryResponse = {
  meeting_id: number;
  html: string;
  file_name: string;
  updated_at: string;
};

export type HtmlSummaryGenerateRequest = {
  show_code?: boolean;
  show_flowchart?: boolean;
};

export type MeetingRegenerateRequest = {
  terms?: string[];
};

export type ChatSessionCreateResponse = {
  session_id: string;
  mode: string;
  meeting_id: number | null;
};

export type ChatMemoryStats = {
  round_count: number;
  max_rounds: number;
  is_full: boolean;
  trimmed: boolean;
};

export type RagResultItem = {
  meeting_id?: number | null;
  chunk_type?: string | null;
  meeting_title: string | null;
  meeting_summary?: string | null;
  chunk_type_label: string | null;
  text: string;
  score: number;
};

export type MeetingSourceType =
  | "transcript"
  | "minutes"
  | "action_item"
  | "resolution";

export type ChatMessageResponse = {
  assistant_message: string;
  rag_results: RagResultItem[];
  memory: ChatMemoryStats;
};

export type RealtimeSegment = {
  start: number;
  end: number;
  timestamp: number;
  text: string;
  speaker?: string | null;
};

export type RealtimeSessionCreateRequest = {
  title?: string;
  meeting_date: string;
  meeting_time: string;
  output_format?: string;
  scene?: string;
  asr_model?: string;
  terms?: string[];
};

export type RealtimeSessionResponse = {
  session_id: string;
  title: string;
  meeting_date: string;
  meeting_time: string;
  output_format: string;
  scene: string;
  asr_model: string;
  terms: string[];
  status: string;
  message: string;
  transcript: string;
  duration_seconds: number;
  chunk_count: number;
  segments: RealtimeSegment[];
  speaker_segments: RealtimeSegment[];
  created_at: string;
  updated_at: string;
};

export type RealtimeSessionMutationResponse = {
  success: boolean;
};
