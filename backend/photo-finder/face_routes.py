from fastapi import APIRouter, UploadFile, File, Form, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.domain.photo_ai.schemas.face_schema import (
    InitializeCollectionRequest,
    InitializeCollectionResponse,
    IndexFacesRequest,
    IndexFacesResponse,
    SearchFaceRequest,
    SearchFaceS3Request,
    SearchFaceResponse,
    ListFacesRequest,
    ListFacesResponse
)
from app.domain.photo_ai.controllers.face_controller import FaceController
from app.core.security.auth_dependency import get_current_user
from app.config.interaction_db import get_interaction_db
from app.domain.auth.models.user_model import User

router = APIRouter(prefix="/photo-ai", tags=["Photo AI - Reconhecimento Facial"])


@router.post("/initialize", response_model=InitializeCollectionResponse)
def initialize_collection(
    body: InitializeCollectionRequest,
    current_user = Depends(get_current_user)
):
    return FaceController.initialize_collection(body)


@router.post("/index-faces", response_model=IndexFacesResponse)
def index_faces(
    body: IndexFacesRequest,
    current_user = Depends(get_current_user)
):
    return FaceController.index_faces(body)


@router.post("/search-face", response_model=SearchFaceResponse)
async def search_face(
    file: UploadFile = File(...),
    threshold: float = Form(70.0),
    max_faces: int = Form(5),
    collection_id: str = Form("caze-rostos"),
    event_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user)
):
    body = SearchFaceRequest(
        threshold=threshold,
        max_faces=max_faces,
        collection_id=collection_id
    )
    return await FaceController.search_face(
        file, 
        body, 
        user_id=current_user.id if current_user else None,
        event_id=event_id
    )


@router.post("/search-face-s3", response_model=SearchFaceResponse)
def search_face_s3(
    body: SearchFaceS3Request,
    current_user = Depends(get_current_user)
):
    return FaceController.search_face_s3(body)


@router.post("/list-faces", response_model=ListFacesResponse)
def list_faces(
    body: ListFacesRequest,
    current_user = Depends(get_current_user)
):
    return FaceController.list_faces(body)


@router.post("/reset")
def reset_collection(
    collection_id: str = "meu_banco_de_rostos",
    current_user = Depends(get_current_user)
):
    ok = FaceController.reset_collection(collection_id)
    return {"success": ok}


@router.get("/download-image")
def download_image(
    url: str = Query(..., description="URL da imagem (CloudFront/S3 do evento)"),
    event_id: int = Query(None, description="ID do evento"),
    event_name: str = Query(None, description="Nome do evento"),
    similarity: str = Query(None, description="Similaridade da busca"),
    current_user: User = Depends(get_current_user),
    interaction_db: Session = Depends(get_interaction_db)
):
    """Proxy que baixa a imagem e retorna com Content-Disposition: attachment para forçar download no navegador."""
    # Registrar o download
    try:
        from app.domain.users.controllers.downloaded_photo_controller import DownloadedPhotoController
        from app.domain.users.schemas.downloaded_photo_schema import CreateDownloadedPhotoRequest
        
        create_request = CreateDownloadedPhotoRequest(
            image_url=url,
            event_id=event_id,
            event_name=event_name,
            similarity=similarity
        )
        DownloadedPhotoController.create_downloaded_photo(
            interaction_db,
            current_user.id,
            create_request
        )
    except Exception as e:
        # Log do erro mas não falha o download
        print(f"Erro ao registrar download: {str(e)}")
    
    return FaceController.download_image(url)
