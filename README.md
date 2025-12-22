# 🖼️ Visual Product Search Batch Processor

Nightly batch-applicatie die productafbeeldingen van InRiver verwerkt naar Vertex AI embeddings en opslaat in Firestore voor vector search.

---

## ⚙️ Functionaliteiten

- **Batch Processing**: Verwerkt grote hoeveelheden producten in configureerbare batches.
- **Incremental Updates**: Overslaat ongewijzigde producten door gebruik van SHA256 image hashing.
- **Vision Embeddings**: Genereert 1408-dimensionale vectoren via Vertex AI Multimodal Embeddings (`multimodalembedding@001`).
- **Firestore Integratie**: Slaat verwerkte data op in Firestore met collecties voor producten, voortgang en foutmeldingen.
- **CLI Interface**: Eenvoudig aan te sturen via command-line arguments voor automatisering.

---

## 🛠️ Gebruik (Lokaal)

### 1. Installatie
Zorg voor een Python 3.10+ omgeving.
```bash
# Systeem dependencies
pip install -r requirements.txt
```

### 2. Configuratie
Maak een `.env` bestand aan met de volgende variabelen:
```bash
# InRiver
IN_RIVER_BASE_URL=https://api-prod1a-euw.productmarketingcloud.com
ECOM_INRIVER_API_KEY=your_inriver_key
INRIVER_IMAGE_FIELD=MainImage

# Google Cloud
GOOGLE_CLOUD_PROJECT=your_project_id
VERTEX_LOCATION=europe-west4
FIRESTORE_PRODUCTS_COLLECTION=products
FIRESTORE_PROGRESS_COLLECTION=batchProgress
FIRESTORE_ERRORS_COLLECTION=processingErrors

# Batch settings
BATCH_SIZE=500
```

### 3. Uitvoeren
Start het batch-proces handmatig:
```bash
python app.py --batch-size 500
```
Voor een test-run zonder data op te slaan:
```bash
python app.py --batch-size 10 --dry-run
```

---

## 🚀 Deployment (Google Cloud Run Jobs)

Hoewel de `cloudbuild.yaml` momenteel nog een Cloud Run *Service* configureert, is dit project geoptimaliseerd om te draaien als een **Cloud Run Job**.

### Aanbevolen Deployment (Job):
```bash
gcloud run jobs deploy visual-search-batch \
  --image gcr.io/your_project/ecom-visual-product-search \
  --tasks 1 \
  --max-retries 0 \
  --region europe-west4
```

### Scannen via Cloud Scheduler:
Configureer een nightly trigger voor de Cloud Run Job om het proces elke nacht automatisch te starten.

---

## 📂 Projectstructuur
- `app.py`: CLI entry point voor batch processing.
- `batch_processor.py`: Hoofd orchestrator voor batch logica & incremental checks.
- `inriver_client.py`: InRiver API adapter.
- `vision_client.py`: Vertex AI Embedding generator.
- `firestore_client.py`: Firestore database adapter.
- `image_utils.py`: Hashing en download utilities.
- `tools/search_tools.py`: Vector search logica voor de agent.
- `adk_app/agent.py`: ADK Visual Search Agent.

---

## 🔍 Vector Search Configureren
Om de zoekfunctie in `adk-web` te gebruiken, moet er een **Vector Index** zijn in Firestore.

1. Ga naar de Firebase/GCP Console -> Firestore -> Indexes.
2. Klik op **Composite** -> **Create Index**.
3. Collectie ID: `products` (of wat je geconfigureerd hebt).
4. Velden:
   - `embedding`: **Vector** (Dimension: 1408, Measure: COSINE)
5. Wacht tot de index is opgebouwd.

---

## 🤖 Visual Search Agent (`adk web`)
Je kunt met `adk web` interactief zoeken door een afbeelding te uploaden:
1. Start `adk web`.
2. Upload een afbeelding.
3. Vraag: "Zoek vergelijkbare producten voor deze afbeelding".
4. De agent gebruikt de `embedding` van de geüploade foto om de top 5 matches in Firestore te vinden.

---

## 📊 Monitoring
Controleer de volgende Firestore collecties voor resultaten:
- `products`: De verwerkte data incl. embeddings.
- `processingErrors`: Logs van mislukte verwerkingen (bijv. corrupte afbeeldingen).

---

## 👤 Beheer
Ontwikkeld voor **Ecom-Applicatiebeheer**.
Uitsluitend voor intern gebruik.