"""
Serviço de reconhecimento facial via AWS Rekognition.
Adaptado do photo-finder para o contexto de vídeos da cabine.
"""
import os
import logging
from typing import Optional
import boto3
from PIL import Image
from io import BytesIO

logger = logging.getLogger(__name__)

REKOGNITION_REGION = os.environ.get("REKOGNITION_REGION", "us-east-1")
COLLECTION_ID = os.environ.get("REKOGNITION_COLLECTION_ID", "hellmanns-event")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")


class RekognitionService:
    def __init__(self):
        self._client = boto3.client(
            "rekognition",
            region_name=REKOGNITION_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )

    def criar_colecao_se_nao_existir(self, collection_id: str = COLLECTION_ID) -> None:
        try:
            self._client.create_collection(CollectionId=collection_id)
            logger.info("Rekognition collection '%s' criada", collection_id)
        except self._client.exceptions.ResourceAlreadyExistsException:
            logger.info("Rekognition collection '%s' já existe", collection_id)
        except Exception as e:
            logger.error("Erro ao criar collection '%s': %s", collection_id, e)
            raise

    @staticmethod
    def _resize_if_needed(image_bytes: bytes, max_mb: int = 4) -> bytes:
        max_bytes = max_mb * 1024 * 1024
        if len(image_bytes) <= max_bytes:
            return image_bytes
        img = Image.open(BytesIO(image_bytes))
        factor = 0.7
        while True:
            w = int(img.width * factor)
            h = int(img.height * factor)
            resized = img.resize((w, h), Image.Resampling.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=85)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                return data
            factor *= 0.8

    def indexar_face(
        self,
        image_bytes: bytes,
        external_image_id: str,
        collection_id: str = COLLECTION_ID,
    ) -> bool:
        """Indexa um frame na collection. external_image_id formato: {session_id}_c{cabine_id}"""
        try:
            image_bytes = self._resize_if_needed(image_bytes)
            response = self._client.index_faces(
                CollectionId=collection_id,
                Image={"Bytes": image_bytes},
                ExternalImageId=external_image_id,
                MaxFaces=3,
                QualityFilter="NONE",  # NONE aceita frames de vídeo com qualidade menor
                DetectionAttributes=[],
            )
            indexed = len(response.get("FaceRecords", []))
            if indexed > 0:
                logger.info("Indexado %s → %d face(s)", external_image_id, indexed)
                return True

            # Loga o motivo da rejeição para debug
            for unindexed in response.get("UnindexedFaces", []):
                reasons = unindexed.get("Reasons", [])
                logger.warning("Face não indexada em %s — motivos: %s", external_image_id, reasons)
            if not response.get("UnindexedFaces"):
                logger.warning("Nenhuma face detectada em %s (frame sem rosto visível)", external_image_id)
            return False
        except Exception as e:
            logger.error("Erro ao indexar face %s: %s", external_image_id, e)
            raise

    def buscar_rosto(
        self,
        image_bytes: bytes,
        collection_id: str = COLLECTION_ID,
        threshold: float = 40.0,
        max_faces: int = 10,
    ) -> list[dict]:
        """
        Busca rostos na collection.
        Retorna lista de dicts: [{external_image_id, similarity, face_id}]
        Retorna [] se nenhum rosto detectado ou nenhum match.
        """
        try:
            image_bytes = self._resize_if_needed(image_bytes)
            detect = self._client.detect_faces(
                Image={"Bytes": image_bytes},
                Attributes=["DEFAULT"],
            )
            if not detect["FaceDetails"]:
                logger.info("Nenhum rosto detectado na imagem de busca")
                return []

            response = self._client.search_faces_by_image(
                CollectionId=collection_id,
                Image={"Bytes": image_bytes},
                MaxFaces=max_faces,
                FaceMatchThreshold=threshold,
            )
            matches = []
            for match in response.get("FaceMatches", []):
                matches.append({
                    "external_image_id": match["Face"]["ExternalImageId"],
                    "similarity": match["Similarity"],
                    "face_id": match["Face"]["FaceId"],
                })
            if matches:
                logger.info("Busca facial: %d match(es) — melhor: %s (%.1f%%)",
                    len(matches), matches[0]["external_image_id"], matches[0]["similarity"])
            else:
                logger.info("Busca facial: nenhum match acima de %.0f%%", threshold)
            return matches
        except Exception as e:
            logger.error("Erro na busca facial: %s", e)
            raise
