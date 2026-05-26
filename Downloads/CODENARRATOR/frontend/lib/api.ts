export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_URL   = (BASE_URL).replace(/^http/, "ws");

export interface GenerateRequest {
  repo_url: string;
  run_video: boolean;
  language: string;
  theme: "dark" | "light" | "cyberpunk";
  voice: string;
  github_token?: string;
}
export interface GenerateResponse { job_id: string }
export interface JobStatus { status: "queued"|"processing"|"completed"|"failed"; progress: number }
export interface LogEntry { timestamp: number; message: string }
export interface LogsResponse { logs: LogEntry[]; total: number }
export interface ChaptersResponse { completed_chapters: string[]; total_chapters: number }
export interface ArtifactsResponse { markdown_files: string[]; video_url: string | null }
export interface SearchResult { file: string; line: number; snippet: string }
export interface SearchResponse { results: SearchResult[] }
export interface AdminStats {
  total_jobs: number; completed_jobs: number; failed_jobs: number; active_jobs: number;
  llm_cache: { entries: number; size_kb: number; provider: string };
  output_dir_size_mb: number;
}
export interface DiskJob {
  job_id: string; md_count: number; has_video: boolean; size_mb: number;
  mtime: number; in_memory: boolean; status: string;
}
export interface QuizQuestion {
  question: string;
  options: string[];
  correct: number;
  explanation: string;
}
export interface QuizResponse {
  questions: QuizQuestion[];
  chapter: string;
}
export interface ExportResult {
  success: boolean;
  url?: string;
  message: string;
}
export interface GitHubUser {
  authenticated: boolean;
  login?: string;
  name?: string;
  avatar_url?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  generate(req: GenerateRequest): Promise<GenerateResponse> {
    return request("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  },
  getStatus(jobId: string): Promise<JobStatus> {
    return request(`/api/jobs/${jobId}/status`);
  },
  getLogs(jobId: string, since = 0): Promise<LogsResponse> {
    return request(`/api/jobs/${jobId}/logs?since=${since}`);
  },
  getChapters(jobId: string): Promise<ChaptersResponse> {
    return request(`/api/jobs/${jobId}/chapters`);
  },
  getArtifacts(jobId: string): Promise<ArtifactsResponse> {
    return request(`/api/jobs/${jobId}/artifacts`);
  },
  fileUrl(jobId: string, filename: string): string {
    return `${BASE_URL}/api/jobs/${jobId}/file/${encodeURIComponent(filename)}`;
  },
  search(jobId: string, q: string): Promise<SearchResponse> {
    return request(`/api/jobs/${jobId}/search?q=${encodeURIComponent(q)}`);
  },
  exportPdfUrl(jobId: string): string {
    return `${BASE_URL}/api/jobs/${jobId}/export/pdf`;
  },
  chat(jobId: string, message: string, contextFile?: string): Promise<{ reply: string }> {
    return request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, message, context_file: contextFile }),
    });
  },

  // ── Quiz ──────────────────────────────────────────────────────────────────
  getQuiz(jobId: string, chapter: string): Promise<QuizResponse> {
    return request(`/api/jobs/${jobId}/quiz/${encodeURIComponent(chapter)}`);
  },

  // ── Notion Export ─────────────────────────────────────────────────────────
  exportToNotion(jobId: string, notionToken: string, parentPageId: string): Promise<ExportResult> {
    return request(`/api/jobs/${jobId}/export/notion`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notion_token: notionToken, parent_page_id: parentPageId }),
    });
  },

  // ── Confluence Export ─────────────────────────────────────────────────────
  exportToConfluence(
    jobId: string,
    confluenceUrl: string,
    username: string,
    apiToken: string,
    spaceKey: string,
    parentPageId?: string,
  ): Promise<ExportResult> {
    return request(`/api/jobs/${jobId}/export/confluence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confluence_url: confluenceUrl, username, api_token: apiToken, space_key: spaceKey, parent_page_id: parentPageId }),
    });
  },

  // ── GitHub Auth ───────────────────────────────────────────────────────────
  githubLoginUrl(): string {
    return `${BASE_URL}/api/auth/github`;
  },
  getMe(token: string): Promise<GitHubUser> {
    return request("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  // ── Admin ─────────────────────────────────────────────────────────────────
  adminStats(): Promise<AdminStats> {
    return request("/api/admin/stats");
  },
  adminDiskJobs(): Promise<{ jobs: DiskJob[] }> {
    return request("/api/admin/disk-jobs");
  },
  adminMemoryJobs(): Promise<{ jobs: any[] }> {
    return request("/api/admin/jobs");
  },
  adminClearCache(): Promise<{ cleared: number; message: string }> {
    return request("/api/admin/cache/clear", { method: "POST" });
  },
  adminProvider(): Promise<Record<string, any>> {
    return request("/api/admin/provider");
  },
  wsUrl(jobId: string): string {
    return `${WS_URL}/ws/jobs/${jobId}`;
  },
};
