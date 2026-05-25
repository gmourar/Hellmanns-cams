import boto3
import os
from PIL import Image
from io import BytesIO
from typing import Tuple, Set, List, Dict, Optional
from app.config.settings import settings
import datetime
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from botocore.signers import CloudFrontSigner


class RekognitionService:
    def __init__(self):
        rekognition_bucket = settings.REKOGNITION_BUCKET or settings.AWS_BUCKET
        rekognition_region = settings.REKOGNITION_REGION
        
        self.rekognition = boto3.client(
            'rekognition',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=rekognition_region
        )
        
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=rekognition_region
        )
        
        self.bucket_name = rekognition_bucket
        self.region = rekognition_region
    
    def preparar_recursos_evento(self, collection_id: str) -> None:

        try:
            prefix = f"{collection_id}/"
            
            # Pasta no bucket
            self.criar_pasta_s3(prefix)
            
            # Coleção no Rekognition
            self.inicializar_colecao(collection_id)
            
            # Indexação inicial (se já houver imagens nesse prefixo)
            try:
                self.indexar_bucket_s3(prefix, collection_id)
            except Exception as e:
                print(f"Falha ao indexar prefixo {prefix} na criação do evento {collection_id}: {e}")
        except Exception as e:
            print(f"Falha ao preparar recursos de IA para collection {collection_id}: {e}")
    
    def criar_pasta_s3(self, prefix: str) -> bool:
 
        try:
            if not prefix:
                return False
            
            prefix_key = prefix if prefix.endswith('/') else f"{prefix}/"
            self.s3.put_object(Bucket=self.bucket_name, Key=prefix_key)
            return True
        except Exception as e:
            print(f"Erro ao criar pasta no S3 ({prefix}): {e}")
            return False
    
    def buscar_nome_completo_s3(self, nome_sem_extensao: str, collection_id: str = "") -> str:
        try:
            prefix_base = f"{collection_id}/" if collection_id else settings.S3_FOLDER
            prefix = f"{prefix_base}{nome_sem_extensao}."
            response = self.s3.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=1
            )
            
            if 'Contents' in response and len(response['Contents']) > 0:
                full_key = response['Contents'][0]['Key']
                if "/" in full_key:
                    return full_key.split("/")[-1]
                return full_key
            
            return nome_sem_extensao
            
        except Exception as e:
            print(f"Erro ao buscar nome completo no S3: {e}")
            return nome_sem_extensao
    
    @staticmethod
    def redimensionar_imagem(image_bytes: bytes, max_size_mb: int = 4) -> bytes:
        max_size_bytes = max_size_mb * 1024 * 1024
        
        if len(image_bytes) <= max_size_bytes:
            return image_bytes
        
        img = Image.open(BytesIO(image_bytes))
        
        fator = 0.7
        while True:
            largura_nova = int(img.width * fator)
            altura_nova = int(img.height * fator)
            img_redimensionada = img.resize((largura_nova, altura_nova), Image.Resampling.LANCZOS)
            
            buffer = BytesIO()
            img_redimensionada.save(buffer, format='JPEG', quality=85, optimize=True)
            buffer.seek(0)
            tamanho_novo = len(buffer.getvalue())
            
            if tamanho_novo <= max_size_bytes:
                return buffer.getvalue()
            
            fator *= 0.8
    
    def inicializar_colecao(self, collection_id: str = "meu_banco_de_rostos") -> Tuple[bool, str]:
        try:
            self.rekognition.create_collection(CollectionId=collection_id)
            return True, f"Coleção '{collection_id}' criada com sucesso."
        except self.rekognition.exceptions.ResourceAlreadyExistsException:
            return True, f"A coleção '{collection_id}' já existe."
        except Exception as e:
            return False, f"Erro ao criar coleção: {str(e)}"
    
    def obter_faces_indexadas(self, collection_id: str = "meu_banco_de_rostos") -> Set[str]:
        try:
            faces_indexadas = set()
            next_token = None
            
            while True:
                if next_token:
                    response = self.rekognition.list_faces(
                        CollectionId=collection_id,
                        MaxResults=4096,
                        NextToken=next_token
                    )
                else:
                    response = self.rekognition.list_faces(
                        CollectionId=collection_id,
                        MaxResults=4096
                    )
                
                for face in response.get('Faces', []):
                    if 'ExternalImageId' in face:
                        faces_indexadas.add(face['ExternalImageId'])
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            return faces_indexadas
        except Exception as e:
            print(f"Erro ao listar faces: {e}")
            return set()

    def reset_collection(self, collection_id: str = "meu_banco_de_rostos") -> bool:
        try:
            try:
                self.rekognition.delete_collection(CollectionId=collection_id)
            except self.rekognition.exceptions.ResourceNotFoundException:
                pass
            self.rekognition.create_collection(CollectionId=collection_id)
            return True
        except Exception as e:
            print(f"Erro ao resetar coleção: {e}")
            return False
    
    def listar_faces(self, collection_id: str = "meu_banco_de_rostos", max_results: int = 4096) -> List[Dict]:

        try:
            faces = []
            next_token = None
            
            while True:
                if next_token:
                    response = self.rekognition.list_faces(
                        CollectionId=collection_id,
                        MaxResults=max_results,
                        NextToken=next_token
                    )
                else:
                    response = self.rekognition.list_faces(
                        CollectionId=collection_id,
                        MaxResults=max_results
                    )
                
                for face in response.get('Faces', []):
                    faces.append({
                        'face_id': face.get('FaceId', ''),
                        'external_image_id': face.get('ExternalImageId', ''),
                        'confidence': face.get('Confidence', 0.0)
                    })
                
                next_token = response.get('NextToken')
                if not next_token:
                    break
            
            return faces
        except Exception as e:
            raise Exception(f"Erro ao listar faces: {str(e)}")
    
    def indexar_bucket_s3(
        self, 
        s3_folder: str = "rostos/", 
        collection_id: str = "meu_banco_de_rostos"
    ) -> Tuple[int, int, int, List[Dict]]:
  
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket_name, Prefix=s3_folder)
            
            if 'Contents' not in response:
                return 0, 0, 0, []
            
            sucesso = 0
            falhas = 0
            puladas = 0
            resultados = []
            
            for obj in response['Contents']:
                s3_key = obj['Key']
                nome_arquivo = os.path.basename(s3_key)
                
                if s3_key == s3_folder or not nome_arquivo:
                    continue
                
                if not nome_arquivo.lower().endswith(('.png', '.jpg', '.jpeg')):
                    continue
                
                try:
                    import re
                    ext = os.path.splitext(nome_arquivo)[1]
                    nome_limpo = os.path.splitext(nome_arquivo)[0]
                    nome_limpo = re.sub(r'[^a-zA-Z0-9_.\-:]', '_', nome_limpo)

                    # Se o nome foi sanitizado, copia o arquivo no S3 com o novo nome
                    pasta = s3_key[: len(s3_key) - len(nome_arquivo)]
                    s3_key_sanitizado = f"{pasta}{nome_limpo}{ext}"
                    if s3_key_sanitizado != s3_key:
                        try:
                            self.s3.copy_object(
                                Bucket=self.bucket_name,
                                CopySource={'Bucket': self.bucket_name, 'Key': s3_key},
                                Key=s3_key_sanitizado
                            )
                        except Exception:
                            s3_key_sanitizado = s3_key

                    index_response = self.rekognition.index_faces(
                        CollectionId=collection_id,
                        Image={
                            'S3Object': {
                                'Bucket': self.bucket_name,
                                'Name': s3_key_sanitizado
                            }
                        },
                        ExternalImageId=nome_limpo,
                        MaxFaces=15,
                        QualityFilter="AUTO",
                        DetectionAttributes=['DEFAULT']
                    )
                    
                    if index_response['FaceRecords']:
                        for rec in index_response['FaceRecords']:
                            face_id = rec['Face']['FaceId']
                            sucesso += 1
                            resultados.append({
                                'filename': nome_arquivo,
                                'external_image_id': nome_limpo,
                                'face_id': face_id,
                                'status': 'success'
                            })
                    else:
                        falhas += 1
                        resultados.append({
                            'filename': nome_arquivo,
                            'external_image_id': nome_limpo,
                            'face_id': '',
                            'status': 'no_face_detected'
                        })
                        
                except Exception as e:
                    falhas += 1
                    resultados.append({
                        'filename': nome_arquivo,
                        'external_image_id': nome_limpo if 'nome_limpo' in locals() else '',
                        'face_id': '',
                        'status': f'error: {str(e)[:50]}'
                    })
            
            return sucesso, puladas, falhas, resultados
            
        except Exception as e:
            raise Exception(f"Erro ao listar objetos no S3: {str(e)}")
    
    def buscar_rosto_por_imagem(
        self,
        image_bytes: bytes,
        collection_id: str = "meu_banco_de_rostos",
        threshold: float = 60.0,
        max_faces: int = 15
    ) -> Tuple[bool, Optional[float], List[Dict]]:
        """
        Busca quem é a pessoa da foto dentro da coleção.
        
        Args:
            image_bytes: Bytes da imagem
            collection_id: ID da coleção
            threshold: Limite de confiança
            max_faces: Máximo de correspondências
            
        Returns:
            Tupla (face_detectada, confianca_detecção, lista_correspondências)
        """
        try:
            image_bytes = self.redimensionar_imagem(image_bytes)
            
            detect_response = self.rekognition.detect_faces(
                Image={'Bytes': image_bytes},
                Attributes=['DEFAULT']
            )
            
            if not detect_response['FaceDetails']:
                return False, None, []
            
            face_confidence = detect_response['FaceDetails'][0]['Confidence']
            
            response = self.rekognition.search_faces_by_image(
                CollectionId=collection_id,
                Image={'Bytes': image_bytes},
                MaxFaces=max_faces,
                FaceMatchThreshold=threshold
            )
            
            matches = []
            for match in response['FaceMatches']:
                external_id = match['Face']['ExternalImageId']
                nome_completo = self.buscar_nome_completo_s3(external_id, collection_id)
                
                s3_key = f"{collection_id}/{nome_completo}"
                image_url = self._gerar_url_assinada_cloudfront(s3_key)
            
                matches.append({
                    'name': external_id,
                    'similarity': match['Similarity'],
                    'face_id': match['Face']['FaceId'],
                    'image_url': image_url
                })
            
            return True, face_confidence, matches
            
        except Exception as e:
            raise Exception(f"Erro na busca: {str(e)}")
    
    def buscar_rosto_s3(
        self,
        s3_key: str,
        collection_id: str = "meu_banco_de_rostos",
        threshold: float = 60.0,
        max_faces: int = 15
    ) -> Tuple[bool, Optional[float], List[Dict]]:
        try:
            detect_response = self.rekognition.detect_faces(
                Image={
                    'S3Object': {
                        'Bucket': self.bucket_name,
                        'Name': s3_key
                    }
                },
                Attributes=['DEFAULT']
            )
            
            if not detect_response['FaceDetails']:
                return False, None, []
            
            face_confidence = detect_response['FaceDetails'][0]['Confidence']
            
            response = self.rekognition.search_faces_by_image(
                CollectionId=collection_id,
                Image={
                    'S3Object': {
                        'Bucket': self.bucket_name,
                        'Name': s3_key
                    }
                },
                MaxFaces=max_faces,
                FaceMatchThreshold=threshold
            )
            
            matches = []
            for match in response['FaceMatches']:
                external_id = match['Face']['ExternalImageId']
                nome_completo = self.buscar_nome_completo_s3(external_id, collection_id)
                image_url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{collection_id}/{nome_completo}"
                matches.append({
                    'name': external_id,
                    'similarity': match['Similarity'],
                    'face_id': match['Face']['FaceId'],
                    'image_url': image_url
                })
            
            return True, face_confidence, matches
            
        except Exception as e:
            raise Exception(f"Erro na busca: {str(e)}")

    def _gerar_url_assinada_cloudfront(self, s3_key: str) -> str:
        """Gera uma URL protegida via CloudFront que expira em 30 minutos."""
        url = f"https://{settings.AWS_CLOUDFRONT_DOMAIN_REKO}/{s3_key}"
        
        try:
            # Carrega a chave privada do arquivo .pem que criamos
            with open(settings.CLOUDFRONT_PRIVATE_KEY_PATH, "rb") as key_file:
                private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=None,
                    backend=default_backend()
                )

            # Função auxiliar para assinar a mensagem
            def rsa_signer(message):
                return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())

            signer = CloudFrontSigner(settings.CLOUDFRONT_PUBLIC_KEY_ID, rsa_signer)
            
            # Expira em 30 minutos
            date_less_than = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
            
            return signer.generate_presigned_url(url, date_less_than=date_less_than)
        except Exception as e:
            print(f"Erro ao gerar URL assinada: {e}")
            return url # Retorna a URL normal em caso de erro (mas ela falhará no browser, o que é seguro)