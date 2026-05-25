import os
import logging
from app.infra.celery_app import celery_app
from app.config.admin_db import AdminSessionLocal
from app.config.interaction_db import SessionLocal as InteractionSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(name='photo_ai.match_new_photos', bind=True, max_retries=3)
def match_new_photos_task(self, event_id: str, new_s3_keys: list):
    from app.domain.photo_ai.services.rekognition_service import RekognitionService
    from app.domain.photo_ai.repositories.user_face_repository import UserFaceRepository
    from app.domain.users.repositories.user_photo_repository import UserPhotoRepository
    from app.infra.onesignal import send_to_user

    users_collection = f"users_{event_id}"
    service = RekognitionService()

    admin_db = AdminSessionLocal()
    interaction_db = InteractionSessionLocal()

    try:
        registered_faces = UserFaceRepository.list_by_event(admin_db, event_id)
        if not registered_faces:
            return {"matched": 0, "processed": len(new_s3_keys), "reason": "no_registered_users"}

        matched_total = 0

        for s3_key in new_s3_keys:
            try:
                filename = os.path.basename(s3_key)
                drive_file_id = os.path.splitext(filename)[0]

                try:
                    detected, _conf, matches = service.buscar_rosto_s3(
                        s3_key=s3_key,
                        collection_id=users_collection,
                        threshold=70.0,
                        max_faces=50,
                    )
                except Exception as e:
                    logger.warning(f"[match_new_photos] Search failed for {s3_key}: {e}")
                    continue

                if not detected or not matches:
                    continue

                for match in matches:
                    try:
                        user_id = int(match['name'])
                    except (ValueError, KeyError):
                        continue

                    existing = UserPhotoRepository.get(interaction_db, user_id, event_id, drive_file_id)
                    if existing:
                        continue

                    UserPhotoRepository.create(interaction_db, {
                        'user_id': user_id,
                        'event_id': event_id,
                        'drive_file_id': drive_file_id,
                        's3_key': s3_key,
                        'similarity': match['similarity'],
                        'notified': False,
                    })
                    matched_total += 1

                    try:
                        send_to_user(
                            user_id=user_id,
                            title="Nova foto sua chegou!",
                            message="Uma foto sua foi encontrada no evento. Toque para ver.",
                        )
                        UserPhotoRepository.mark_notified(interaction_db, user_id, event_id, drive_file_id)
                    except Exception as e:
                        logger.warning(f"[match_new_photos] Push failed for user {user_id}: {e}")

            except Exception as e:
                logger.error(f"[match_new_photos] Error processing {s3_key}: {e}")

        logger.info(f"[match_new_photos] event={event_id} matched={matched_total} keys={len(new_s3_keys)}")
        return {"matched": matched_total, "processed": len(new_s3_keys)}

    except Exception as e:
        logger.exception(f"[match_new_photos] Fatal error for event {event_id}: {e}")
        raise self.retry(exc=e, countdown=60)
    finally:
        admin_db.close()
        interaction_db.close()
