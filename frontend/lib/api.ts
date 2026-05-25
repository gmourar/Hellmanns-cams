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
