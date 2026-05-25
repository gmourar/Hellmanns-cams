"use client";

import api from "@/app/services/auth/axiosConfig";

interface SearchFaceResponse {
  images?: string[];
  matches?: Array<{
    image_url?: string;
    url?: string;
    image?: string;
    name?: string;
    external_image_id?: string;
    similarity?: number;
  }>;
  message?: string;
}

export async function searchFace(
  file: File,
  collectionId?: string,
  eventId?: number
): Promise<SearchFaceResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("threshold", "70");
  formData.append("max_faces", "100"); // mais faces para fotos de grupo
  if (collectionId) formData.append("collection_id", collectionId);
  if (eventId) formData.append("event_id", eventId.toString());

  const { data } = await api.post<SearchFaceResponse>(
    "/photo-ai/search-face",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );

  return data;
}
