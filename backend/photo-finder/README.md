# Photo Finder — Documentação Técnica

> Sistema de reconhecimento facial que encontra automaticamente fotos de um usuário tiradas durante o evento, usando AWS Rekognition.

---

## Sumário

1. [Como funciona — visão geral](#1-como-funciona--visão-geral)
2. [Arquitetura e arquivos](#2-arquitetura-e-arquivos)
3. [Bancos de dados](#3-bancos-de-dados)
4. [Fluxo 1 — Cadastro de rosto do usuário](#4-fluxo-1--cadastro-de-rosto-do-usuário)
5. [Fluxo 2 — Sincronização de fotos do evento](#5-fluxo-2--sincronização-de-fotos-do-evento)
6. [Fluxo 3 — Busca manual de fotos](#6-fluxo-3--busca-manual-de-fotos)
7. [Fluxo 4 — Notificação automática](#7-fluxo-4--notificação-automática)
8. [Endpoints da API](#8-endpoints-da-api)
9. [Variáveis de ambiente necessárias](#9-variáveis-de-ambiente-necessárias)
10. [Conceitos AWS Rekognition](#10-conceitos-aws-rekognition)
11. [Limitações conhecidas](#11-limitações-conhecidas)

---

## 1. Como funciona — visão geral

```
FOTÓGRAFO                   BACKEND (Celery)            AWS
    │                             │                       │
    │ Tira fotos no evento        │                       │
    ▼                             │                       │
[Google Drive] ──sync robot──► [S3 Bucket]               │
                                  │                       │
                                  │── index_faces() ────► [Rekognition Collection]
                                  │                       │ (vetores das faces)
                                  │                       │
USUÁRIO                           │                       │
    │                             │                       │
    │ Cadastra selfie              │                       │
    ▼                             │                       │
[App - /foto] ── register_face ─► [S3: users_{event_id}] │
                                  │── index_faces() ────► [Rekognition Collection users_X]
                                  │
                                  │ Celery Task (match_new_photos_task)
                                  │── search_faces_by_image() ─► matches
                                  │
                                  ▼
                           [interaction_db: user_photos]
                                  │
                                  │── push notification ─► USUÁRIO
```

**Resumo em 3 etapas:**
1. Fotos do evento são sincronizadas do Google Drive para o S3 e indexadas no Rekognition
2. Usuário cadastra o próprio rosto (selfie), que também é indexado em uma coleção separada
3. A task Celery cruza as fotos novas com os rostos cadastrados e notifica quem foi encontrado

---

## 2. Arquitetura e arquivos

### Backend — `back-n1/`

```
app/domain/photo_ai/
├── controllers/
│   └── face_controller.py        # Orquestra chamadas entre rota e serviço
├── models/
│   ├── user_face_model.py        # ORM: rostos cadastrados pelos usuários
│   └── face_search_model.py      # ORM: histórico/analytics de buscas
├── repositories/
│   └── user_face_repository.py   # CRUD no banco para user_face
├── routes/
│   └── face_routes.py            # Endpoints FastAPI /photo-ai/*
├── schemas/
│   └── face_schema.py            # Pydantic: request/response contracts
├── services/
│   └── rekognition_service.py    # Integração direta com boto3/Rekognition
└── tasks/
    └── face_matching_tasks.py    # Celery: cruza fotos novas com rostos cadastrados

app/domain/users/
├── models/
│   ├── user_photo_model.py       # ORM: fotos encontradas por usuário
│   └── downloaded_photo_model.py # ORM: fotos baixadas pelo usuário
├── repositories/
│   ├── user_photo_repository.py
│   └── downloaded_photo_repository.py
├── controllers/
│   └── downloaded_photo_controller.py
└── routes/
    └── downloaded_photo_routes.py  # GET /downloaded-photos

app/domain/admin/
├── models/photo_sync_log_model.py  # ORM: log do robô de sync
├── routes/photo_sync_routes.py     # GET /admin/photo-sync/status
└── services/photo_sync_service.py  # Dispara match_new_photos_task
```

### Frontend — `front/`

```
app/pages/user/
├── foto/page.tsx          # Página principal do Photo Finder
└── my-photos/page.tsx     # Galeria de fotos baixadas

app/components/home/
└── PhotoAI.tsx            # Wrapper com carregamento dinâmico e tema do evento

app/services/ai/
├── searchFaceService.ts   # POST /photo-ai/search-face
└── userFaceService.ts     # GET/POST/DELETE /photo-ai/my-face-status, register-face, etc.

app/services/myPhotos/
└── myPhotosService.ts     # GET /downloaded-photos
```

---

## 3. Bancos de dados

| Banco | Tabela | O que armazena |
|---|---|---|
| `admin_db` | `user_faces` | Qual usuário cadastrou rosto em qual evento, e o `rekognition_face_id` |
| `admin_db` | `face_searches` | Analytics: quando, quem, quantos matches, threshold usado |
| `admin_db` | `photo_sync_logs` | Logs do robô de sync (arquivos novos, indexados, erros) |
| `interaction_db` | `user_photos` | Fotos do evento que foram associadas a um usuário via matching |
| `interaction_db` | `downloaded_photos` | Fotos que o usuário clicou para baixar |

---

## 4. Fluxo 1 — Cadastro de rosto do usuário

O usuário tira uma selfie dentro do app para se "cadastrar" no evento.

**Frontend (`userFaceService.ts`):**
```ts
export async function registerFace(file: File, eventId: number) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("event_id", String(eventId));
  const res = await api.post("/photo-ai/register-face", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data; // { success: boolean, message: string }
}
```

**Backend — o que acontece:**
1. Recebe o arquivo de imagem via multipart
2. Faz upload da selfie para o S3 com a chave `users_{event_id}/{user_id}.jpg`
3. Chama `rekognition.index_faces()` nessa imagem, apontando para a **Collection de usuários** (`users_{event_id}`)
4. Salva na tabela `user_faces` do `admin_db`: `user_id`, `event_id`, `rekognition_face_id`, `collection_id`

**Resultado:** O vetor matemático do rosto do usuário está indexado na AWS. A partir daí, qualquer foto nova do evento pode ser comparada contra ele.

---

## 5. Fluxo 2 — Sincronização de fotos do evento

Um **robô externo** (serviço Linux systemd em `scripts/photo_sync/`) monitora o Google Drive do fotógrafo e, quando detecta fotos novas:

1. Faz upload das fotos para o S3 no prefixo `{collection_id}/`
2. Chama `POST /admin/photo-sync/heartbeat` avisando o backend com as `new_s3_keys`
3. O backend dispara a task Celery `match_new_photos_task`

**Task Celery (`face_matching_tasks.py`):**
```python
@celery_app.task(name='photo_ai.match_new_photos', bind=True, max_retries=3)
def match_new_photos_task(self, event_id: str, new_s3_keys: list):
    users_collection = f"users_{event_id}"
    service = RekognitionService()

    # Busca todos os usuários cadastrados nesse evento
    registered_faces = UserFaceRepository.list_by_event(admin_db, event_id)

    for s3_key in new_s3_keys:
        # Compara cada foto nova contra os rostos cadastrados
        detected, _conf, matches = service.buscar_rosto_s3(
            s3_key=s3_key,
            collection_id=users_collection,
            threshold=70.0,
            max_faces=50,
        )

        for match in matches:
            user_id = int(match['name'])  # ExternalImageId = user_id
            # Salva associação foto ↔ usuário no banco
            UserPhotoRepository.create(interaction_db, {
                'user_id': user_id,
                'event_id': event_id,
                's3_key': s3_key,
                'similarity': match['similarity'],
            })
            # Envia push notification
            send_to_user(user_id, "Nova foto sua chegou!", "...")
```

**Por que duas Collections?**
- `{collection_id}` → fotos do evento (indexadas por nome de arquivo)
- `users_{event_id}` → selfies dos usuários (indexadas por `user_id`)

O matching funciona procurando a face da foto nova **dentro da collection de usuários** — não o contrário.

---

## 6. Fluxo 3 — Busca manual de fotos

O usuário pode também fazer uma busca manual: envia uma foto e o sistema retorna todas as fotos do evento onde aquela face aparece.

**Frontend (`searchFaceService.ts`):**
```ts
export async function searchFace(file: File, collectionId?: string, eventId?: number) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("threshold", "70");    // mínimo 70% de similaridade
  formData.append("max_faces", "100");   // retorna até 100 matches
  if (collectionId) formData.append("collection_id", collectionId);
  if (eventId) formData.append("event_id", eventId.toString());

  const { data } = await api.post("/photo-ai/search-face", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
  // { success, face_detected, face_confidence, matches: [{ name, similarity, image_url }] }
}
```

**Backend — `RekognitionService.buscar_rosto_por_imagem()`:**
```python
def buscar_rosto_por_imagem(self, image_bytes, collection_id, threshold, max_faces):
    # 1. Redimensiona se > 4MB (limite do Rekognition)
    image_bytes = self.redimensionar_imagem(image_bytes)

    # 2. Verifica se há rosto na imagem
    detect_response = self.rekognition.detect_faces(
        Image={'Bytes': image_bytes},
        Attributes=['DEFAULT']
    )
    if not detect_response['FaceDetails']:
        return False, None, []  # sem rosto detectado

    face_confidence = detect_response['FaceDetails'][0]['Confidence']

    # 3. Busca na Collection as fotos que contêm esse rosto
    response = self.rekognition.search_faces_by_image(
        CollectionId=collection_id,
        Image={'Bytes': image_bytes},
        MaxFaces=max_faces,
        FaceMatchThreshold=threshold
    )

    matches = []
    for match in response['FaceMatches']:
        external_id = match['Face']['ExternalImageId']  # nome do arquivo
        # Gera URL assinada do CloudFront (expira em 30 min)
        s3_key = f"{collection_id}/{nome_completo}"
        image_url = self._gerar_url_assinada_cloudfront(s3_key)
        matches.append({
            'name': external_id,
            'similarity': match['Similarity'],
            'face_id': match['Face']['FaceId'],
            'image_url': image_url
        })

    return True, face_confidence, matches
```

**Resposta para o frontend:**
```json
{
  "success": true,
  "face_detected": true,
  "face_confidence": 99.7,
  "matches": [
    {
      "name": "DSC_0042",
      "similarity": 94.3,
      "face_id": "abc-123-...",
      "image_url": "https://d1xxx.cloudfront.net/event-collection/DSC_0042.jpg?Signature=..."
    }
  ],
  "message": "Encontradas 3 correspondência(s)"
}
```

---

## 7. Fluxo 4 — Notificação automática

Quando a task Celery encontra um match, envia push notification via **OneSignal**:

```python
send_to_user(
    user_id=user_id,
    title="Nova foto sua chegou!",
    message="Uma foto sua foi encontrada no evento. Toque para ver.",
)
UserPhotoRepository.mark_notified(interaction_db, user_id, event_id, drive_file_id)
```

O usuário recebe notificação no celular e ao tocar vai direto para a galeria `/my-photos`.

---

## 8. Endpoints da API

Todos exigem autenticação via JWT no header `Authorization: Bearer <token>`.

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/photo-ai/initialize` | Cria uma Collection no Rekognition (admin) |
| `POST` | `/photo-ai/index-faces` | Indexa todas as imagens de uma pasta S3 (admin) |
| `POST` | `/photo-ai/search-face` | Busca fotos enviando uma imagem (multipart) |
| `POST` | `/photo-ai/search-face-s3` | Busca fotos a partir de uma chave S3 |
| `POST` | `/photo-ai/register-face` | Cadastra selfie do usuário |
| `GET` | `/photo-ai/my-face-status` | Verifica se o usuário tem rosto cadastrado |
| `GET` | `/photo-ai/my-photos` | Fotos do evento associadas ao usuário |
| `DELETE` | `/photo-ai/my-face` | Remove rosto cadastrado do usuário |
| `GET` | `/photo-ai/download-image` | Proxy seguro para download (grava no banco) |
| `POST` | `/photo-ai/list-faces` | Lista faces indexadas em uma Collection (admin) |
| `POST` | `/photo-ai/reset` | Reseta uma Collection (admin) |
| `GET` | `/downloaded-photos` | Galeria de fotos baixadas pelo usuário |
| `GET` | `/admin/photo-sync/status` | Status do robô de sincronização |

### Exemplo — `POST /photo-ai/search-face`

**Request (multipart/form-data):**
```
file        = <arquivo de imagem>
threshold   = 70          (float, % mínima de similaridade)
max_faces   = 100         (int, máximo de resultados)
collection_id = "caze-rostos"
event_id    = 42
```

**Response 200:**
```json
{
  "success": true,
  "face_detected": true,
  "face_confidence": 99.7,
  "matches": [
    {
      "name": "DSC_0042",
      "similarity": 94.3,
      "face_id": "a1b2c3d4-...",
      "image_url": "https://cdn.cloudfront.net/...?Signature=..."
    }
  ],
  "message": "Encontradas 1 correspondência(s)"
}
```

**Response quando não detecta rosto:**
```json
{
  "success": false,
  "face_detected": false,
  "face_confidence": null,
  "matches": [],
  "message": "Nenhuma face detectada na imagem"
}
```

---

## 9. Variáveis de ambiente necessárias

```bash
# AWS
AWS_ACCESS_KEY=AKIA...
AWS_SECRET_KEY=...
AWS_REGION=sa-east-1
AWS_BUCKET=nome-do-bucket          # bucket principal
REKOGNITION_BUCKET=nome-do-bucket  # pode ser o mesmo ou separado
REKOGNITION_REGION=us-east-1       # Rekognition só funciona em regiões específicas

# CloudFront (para URLs assinadas das fotos)
AWS_CLOUDFRONT_DOMAIN_REKO=d1xxxxx.cloudfront.net
CLOUDFRONT_PUBLIC_KEY_ID=APKA...   # ID da chave pública no CloudFront
CLOUDFRONT_PRIVATE_KEY_PATH=/path/to/private_key.pem  # arquivo .pem local

# OneSignal (push notifications)
ONESIGNAL_APP_ID=...
ONESIGNAL_API_KEY=...
```

**Atenção:** O Rekognition só está disponível em regiões específicas da AWS. A mais usada é `us-east-1`. O bucket S3 pode estar em `sa-east-1` (São Paulo), mas o cliente Rekognition precisa apontar para uma região que suporte o serviço.

---

## 10. Conceitos AWS Rekognition

### Collection
Uma **Collection** é um banco de vetores de faces armazenado na AWS. Não armazena imagens — só os vetores matemáticos gerados a partir delas. Cada vetor tem um `FaceId` único e um `ExternalImageId` que você define (normalmente o nome do arquivo).

### index_faces()
Processa uma imagem, detecta todos os rostos, gera vetores e os armazena na Collection. Pode indexar até 15 faces por imagem (`MaxFaces=15`). O `ExternalImageId` é o identificador que você vai receber nos resultados de busca — no projeto, usamos o **nome do arquivo** para fotos do evento e o **user_id** para selfies.

### search_faces_by_image()
Recebe uma imagem, detecta o rosto principal e compara contra todos os vetores da Collection. Retorna os matches com score de similaridade (0–100%). O parâmetro `FaceMatchThreshold` define o mínimo aceito (70% no projeto).

### detect_faces()
Apenas detecta se há rostos na imagem e retorna metadados (bounding box, confiança, landmarks). Usado antes do `search_faces_by_image` para validar que a imagem tem rosto antes de chamar a busca.

### URL Assinada CloudFront
As fotos ficam em um bucket S3 privado e são servidas via CloudFront com URLs assinadas que expiram em 30 minutos. Isso evita que links vazem e que as fotos fiquem acessíveis publicamente. O backend assina a URL com uma chave privada RSA registrada no CloudFront.

---

## 11. Limitações conhecidas

| Limitação | Detalhe |
|---|---|
| **1 Collection por evento** | Trocar `REKOGNITION_COLLECTION` no `.env` a cada evento novo. Ou criar programaticamente via `POST /photo-ai/initialize` |
| **Tamanho máximo da imagem** | 4MB para o Rekognition via bytes. O `redimensionar_imagem()` comprime automaticamente com Pillow |
| **Qualidade do rosto** | Rostos muito de perfil (> 45°), ocluídos, ou com menos de 35px de altura não são indexados |
| **Custo AWS** | Cobrado por face indexada (`index_faces`) e por busca (`search_faces_by_image`). Em eventos grandes, monitorar via AWS Cost Explorer |
| **LGPD** | O app exige consentimento explícito antes de ativar o Photo Finder. O aceite é gravado no `auth_db` |
| **Região** | Rekognition não está disponível em `sa-east-1`. Usar `us-east-1` e aceitar a latência extra (~200ms) |
| **Faces similares** | Gêmeos ou pessoas muito parecidas podem gerar falsos positivos. O threshold de 70% equilibra precisão e recall |
