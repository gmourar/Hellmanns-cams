// API client compartilhado entre as duas rotas (operador e galeria)
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8001";

export interface StartSessionResponse {
  session_id: string;
  status: "queued" | "recording";
  started_at: string;
}

export interface GallerySession {
  session_id: string;
  participants: string[];
  videos: GalleryVideo[];
  video_urls: string[];
  status: "recording" | "ready" | "error";
  indexing_status: "pending" | "indexing" | "indexed" | "error";
  created_at: string;
}

export interface GalleryVideo {
  cabine_id: number;
  video_url: string;
  qr_url: string;
}

export async function startSession(payload: {
  operator_name: string;
  participants: string[];
}): Promise<StartSessionResponse> {
  const r = await fetch(`${API_BASE}/operator/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`startSession falhou: ${r.status}`);
  return r.json();
}

export async function getGallery(sessionId: string): Promise<GallerySession> {
  const r = await fetch(`${API_BASE}/gallery/${sessionId}`, { cache: "no-store" });
  if (r.status === 404) throw new Error("Sessão ainda processando ou inexistente");
  if (!r.ok) throw new Error(`getGallery falhou: ${r.status}`);
  return r.json();
}

export interface BuscarVideoResponse {
  session_id: string;
  cabine_id: number;
  video_url: string;
  similarity: number;
}

export interface SessionSummary {
  session_id: string;
  operator_name: string;
  participants: string[];
  created_at: string;
  indexing_status: string;
  videos: GalleryVideo[];
}

export async function getSessions(): Promise<SessionSummary[]> {
  const r = await fetch(`${API_BASE}/sessions`, { cache: "no-store" });
  if (!r.ok) throw new Error(`getSessions falhou: ${r.status}`);
  return r.json();
}

export async function buscarVideo(imagemBase64: string): Promise<BuscarVideoResponse> {
  const r = await fetch(`${API_BASE}/buscar-video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ imagem_base64: imagemBase64 }),
  });
  if (r.status === 404) throw new Error("Rosto não encontrado. Tente novamente em instantes.");
  if (!r.ok) throw new Error(`Erro ao buscar vídeo: ${r.status}`);
  return r.json();
}
