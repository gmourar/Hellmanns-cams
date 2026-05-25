"use client";

import api from "@/app/services/auth/axiosConfig";
import { extractApiError } from "@/app/services/apiError";

export interface MyPhoto {
  drive_file_id: string;
  s3_key: string;
  image_url: string;
  similarity: number | null;
  associated_at: string | null;
}

export interface FaceStatus {
  registered: boolean;
  registered_at?: string | null;
}

export async function getMyFaceStatus(eventId: number): Promise<FaceStatus> {
  try {
    const res = await api.get<FaceStatus>("/photo-ai/my-face-status", {
      params: { event_id: eventId },
    });
    return res.data;
  } catch (e) {
    throw new Error(extractApiError(e, "Erro ao verificar status do rosto"));
  }
}

export async function getMyPhotos(eventId: number): Promise<MyPhoto[]> {
  try {
    const res = await api.get<MyPhoto[]>("/photo-ai/my-photos", {
      params: { event_id: eventId },
    });
    return res.data;
  } catch (e) {
    throw new Error(extractApiError(e, "Erro ao carregar suas fotos"));
  }
}

export async function registerFace(
  file: File,
  eventId: number
): Promise<{ success: boolean; message: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("event_id", String(eventId));
  try {
    const res = await api.post<{ success: boolean; message: string }>("/photo-ai/register-face", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  } catch (e) {
    throw new Error(extractApiError(e, "Erro ao cadastrar rosto"));
  }
}

export async function deleteMyFace(
  eventId: number
): Promise<{ success: boolean }> {
  try {
    const res = await api.delete<{ success: boolean }>("/photo-ai/my-face", {
      params: { event_id: eventId },
    });
    return res.data;
  } catch (e) {
    throw new Error(extractApiError(e, "Erro ao remover rosto"));
  }
}
