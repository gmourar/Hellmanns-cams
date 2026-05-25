from fastapi import UploadFile, HTTPException
from fastapi.responses import Response
import httpx
from app.config.settings import settings
from app.domain.photo_ai.services.rekognition_service import RekognitionService
from app.domain.photo_ai.models.face_search_model import FaceSearch
from app.config.admin_db import AdminSessionLocal
from app.domain.photo_ai.schemas.face_schema import (
    InitializeCollectionRequest,
    InitializeCollectionResponse,
    IndexFacesRequest,
    IndexFacesResponse,
    FaceIndexResult,
    SearchFaceRequest,
    SearchFaceS3Request,
    SearchFaceResponse,
    FaceMatch,
    ListFacesRequest,
    ListFacesResponse,
    FaceInfo
)


class FaceController:
    @staticmethod
    def initialize_collection(body: InitializeCollectionRequest) -> InitializeCollectionResponse:
        service = RekognitionService()
        success, message = service.inicializar_colecao(body.collection_id)
        
        return InitializeCollectionResponse(
            success=success,
            message=message,
            collection_id=body.collection_id
        )
    
    @staticmethod
    def index_faces(body: IndexFacesRequest) -> IndexFacesResponse:
        service = RekognitionService()
        service.inicializar_colecao(body.collection_id)
        sucesso, puladas, falhas, resultados = service.indexar_bucket_s3(
            body.s3_folder,
            body.collection_id
        )
        
        results = [
            FaceIndexResult(
                filename=r['filename'],
                external_image_id=r['external_image_id'],
                face_id=r['face_id'],
                status=r['status']
            )
            for r in resultados
        ]
        
        return IndexFacesResponse(
            success=True,
            total_indexed=sucesso,
            total_skipped=puladas,
            total_failed=falhas,
            results=results,
            message=f"Indexação concluída: {sucesso} indexadas, {puladas} puladas, {falhas} falhas"
        )
    
    @staticmethod
    async def search_face(
        file: UploadFile,
        body: SearchFaceRequest,
        user_id: int = None,
        event_id: int = None
    ) -> SearchFaceResponse:
        service = RekognitionService()
        image_bytes = await file.read()
        
        try:
            face_detected, confidence, matches = service.buscar_rosto_por_imagem(
                image_bytes,
                body.collection_id,
                body.threshold,
                body.max_faces
            )
        except Exception as e:
            # Registrar busca mesmo em caso de erro
            if event_id:
                FaceController._save_face_search(
                    user_id=user_id,
                    event_id=event_id,
                    collection_id=body.collection_id,
                    threshold=body.threshold,
                    max_faces=body.max_faces,
                    face_detected=False,
                    face_confidence=None,
                    matches_count=0
                )
            
            return SearchFaceResponse(
                success=False,
                face_detected=False,
                face_confidence=None,
                matches=[],
                message=str(e)
            )
        
        if not face_detected:
            # Registrar busca sem face detectada
            if event_id:
                FaceController._save_face_search(
                    user_id=user_id,
                    event_id=event_id,
                    collection_id=body.collection_id,
                    threshold=body.threshold,
                    max_faces=body.max_faces,
                    face_detected=False,
                    face_confidence=None,
                    matches_count=0
                )
            
            return SearchFaceResponse(
                success=False,
                face_detected=False,
                face_confidence=None,
                matches=[],
                message="Nenhuma face detectada na imagem"
            )
        
        face_matches = [
            FaceMatch(
                name=m['name'],
                similarity=m['similarity'],
                face_id=m['face_id'],
                image_url=m['image_url']
            )
            for m in matches
        ]
        
        matches_count = len(face_matches)
        
        # Registrar busca com sucesso
        if event_id:
            FaceController._save_face_search(
                user_id=user_id,
                event_id=event_id,
                collection_id=body.collection_id,
                threshold=body.threshold,
                max_faces=body.max_faces,
                face_detected=True,
                face_confidence=confidence,
                matches_count=matches_count
            )
        
        if not face_matches:
            return SearchFaceResponse(
                success=True,
                face_detected=True,
                face_confidence=confidence,
                matches=[],
                message=f"Face detectada mas nenhuma correspondência encontrada com threshold de {body.threshold}%"
            )
        
        return SearchFaceResponse(
            success=True,
            face_detected=True,
            face_confidence=confidence,
            matches=face_matches,
            message=f"Encontradas {matches_count} correspondência(s)"
        )
    
    @staticmethod
    def search_face_s3(body: SearchFaceS3Request) -> SearchFaceResponse:
        service = RekognitionService()
        try:
            face_detected, confidence, matches = service.buscar_rosto_s3(
                body.s3_key,
                body.collection_id,
                body.threshold,
                body.max_faces
            )
        except Exception as e:
            return SearchFaceResponse(
                success=False,
                face_detected=False,
                face_confidence=None,
                matches=[],
                message=str(e)
            )
        
        if not face_detected:
            return SearchFaceResponse(
                success=False,
                face_detected=False,
                face_confidence=None,
                matches=[],
                message="Nenhuma face detectada na imagem"
            )
        
        face_matches = [
            FaceMatch(
                name=m['name'],
                similarity=m['similarity'],
                face_id=m['face_id'],
                image_url=m['image_url']
            )
            for m in matches
        ]
        
        if not face_matches:
            return SearchFaceResponse(
                success=True,
                face_detected=True,
                face_confidence=confidence,
                matches=[],
                message=f"Face detectada mas nenhuma correspondência encontrada com threshold de {body.threshold}%"
            )
        
        return SearchFaceResponse(
            success=True,
            face_detected=True,
            face_confidence=confidence,
            matches=face_matches,
            message=f"Encontradas {len(face_matches)} correspondência(s)"
        )
    
    @staticmethod
    def list_faces(body: ListFacesRequest) -> ListFacesResponse:
        service = RekognitionService()
        faces = service.listar_faces(body.collection_id, body.max_results)
        face_infos = [
            FaceInfo(
                face_id=f['face_id'],
                external_image_id=f['external_image_id'],
                confidence=f['confidence']
            )
            for f in faces
        ]
        
        return ListFacesResponse(
            success=True,
            total_faces=len(face_infos),
            faces=face_infos,
            message=f"Total de {len(face_infos)} face(s) indexada(s)"
        )

    @staticmethod
    def reset_collection(collection_id: str) -> bool:
        service = RekognitionService()
        return service.reset_collection(collection_id)

    @staticmethod
    def _save_face_search(
        user_id: int = None,
        event_id: int = None,
        collection_id: str = None,
        threshold: float = None,
        max_faces: int = None,
        face_detected: bool = None,
        face_confidence: float = None,
        matches_count: int = 0
    ):
        """Salva uma busca de face no banco de dados"""
        if not event_id:
            return
        
        db = AdminSessionLocal()
        try:
            face_search = FaceSearch(
                user_id=user_id,
                event_id=event_id,
                collection_id=collection_id or "meu_banco_de_rostos",
                threshold=threshold,
                max_faces=max_faces,
                face_detected=face_detected,
                face_confidence=face_confidence,
                matches_count=matches_count
            )
            db.add(face_search)
            db.commit()
        except Exception as e:
            db.rollback()
            # Log do erro mas não falha a busca
            print(f"Erro ao salvar busca de face: {str(e)}")
        finally:
            db.close()

    @staticmethod
    def download_image(image_url: str) -> Response:
        """Valida que a URL é do nosso CloudFront/S3, baixa a imagem e retorna com Content-Disposition: attachment."""
        allowed_prefixes = [
            f"https://{settings.AWS_CLOUDFRONT_DOMAIN_REKO}/",
            f"https://{settings.AWS_BUCKET}.s3.",
        ]
        if getattr(settings, "REKOGNITION_BUCKET", None):
            allowed_prefixes.append(f"https://{settings.REKOGNITION_BUCKET}.s3.")
        if not any(image_url.startswith(p) for p in allowed_prefixes):
            raise HTTPException(status_code=400, detail="URL de imagem não permitida")
        try:
            with httpx.Client(timeout=30.0) as client:
                r = client.get(image_url)
                r.raise_for_status()
                content = r.content
                content_type = r.headers.get("content-type", "image/jpeg")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Erro ao obter a imagem: {str(e)}")
        filename = "foto.png" if "image/png" in content_type else "foto.jpg"
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
