from pydantic import BaseModel
from typing import Optional, List


class InitializeCollectionRequest(BaseModel):
    collection_id: Optional[str] = "meu_banco_de_rostos"


class InitializeCollectionResponse(BaseModel):
    success: bool
    message: str
    collection_id: str


class IndexFacesRequest(BaseModel):
    s3_folder: Optional[str] = "rostos/"
    collection_id: Optional[str] = "meu_banco_de_rostos"


class FaceIndexResult(BaseModel):
    filename: str
    external_image_id: str
    face_id: str
    status: str


class IndexFacesResponse(BaseModel):
    success: bool
    total_indexed: int
    total_skipped: int
    total_failed: int
    results: List[FaceIndexResult]
    message: str


class SearchFaceRequest(BaseModel):
    threshold: Optional[float] = 60.0
    max_faces: Optional[int] = 15
    collection_id: Optional[str] = "meu_banco_de_rostos"


class SearchFaceS3Request(BaseModel):
    s3_key: str
    threshold: Optional[float] = 60.0
    max_faces: Optional[int] = 15
    collection_id: Optional[str] = "meu_banco_de_rostos"


class FaceMatch(BaseModel):
    name: str
    similarity: float
    face_id: str
    image_url: str


class SearchFaceResponse(BaseModel):
    success: bool
    face_detected: bool
    face_confidence: Optional[float] = None
    matches: List[FaceMatch]
    message: str


class ListFacesRequest(BaseModel):
    collection_id: Optional[str] = "meu_banco_de_rostos"
    max_results: Optional[int] = 4096


class FaceInfo(BaseModel):
    face_id: str
    external_image_id: str
    confidence: Optional[float] = None


class ListFacesResponse(BaseModel):
    success: bool
    total_faces: int
    faces: List[FaceInfo]
    message: str
