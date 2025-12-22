## 🧠 Ecom-Applicatiebeheer (The Sting AI Agent) Service

Een AI-aangedreven Python- ADK-project dat automatisch productnamen en productomschrijvingen genereert op basis van:
- productdata uit inRiver PIM,
- visuele analyse van mode-afbeeldingen (via GPT-4o Vision of Vertex Gemini Vision),
- uitgebreide system-prompt (docx-bestand)
- vergelijkbare bestaande producten uit InRiver export (RAG-bestand met Excel).

De output bestaat uit commerciële productnamen en productomschrijvingen, volledig afgestemd op de tone of voice van Costes Fashion en haar sub-brands.

---

## ⚙️ Functionaliteiten

✅ Ophalen van entity data uit de inRiver API  
✅ Automatische visuele analyse van kledingstukken (m.b.v. GPT-4o of Gemini)  
✅ RAG-ondersteunde tekstgeneratie op basis van Excel met eerdere teksten  
✅ Output direct terugschrijven naar inRiver  
✅ Klaar voor automatische hosting via Google Cloud Run
✅ CI/CD via GitHub → Google Cloud Build

---

## 📂 Projectstructuur

```plaintext
├── adapters/                     # Koppelingen met verschillende LLM-providers
│   ├── llm_openai.py             # OpenAI integratie
│   ├── llm_vertex.py             # Vertex AI integratie
│   └── llm_provider.py           # Abstractielaag voor meerdere LLMs
│
├── adk_app/                      # ADK-agent logica
│   └── agent.py                  # Hoofd orchestrator-agent
│
├── agents/                       # Subagents
│   ├── copy_subagent.py          # Genereert productnamen en -omschrijvingen
│   └── vision_subagent.py        # Analyseert kledingafbeeldingen
│
├── prompts/
│   └── Prompt_productomschrijvingen_costes_V2.docx   # System prompt richtlijnen
│
├── rag_data/
│   └── InRiverExport2025online_items_Costes.xlsx     # RAG-bronbestand met voorbeeldteksten
│
├── tools/
│   └── inriver_api.py            # API-adapter voor InRiver-data
│
├── app.py                        # Entry point van de applicatie
├── requirements.txt              # Vereiste Python-pakketten
├── Dockerfile                    # Voor containerisatie
├── cloudbuild.yaml               # CI/CD-configuratie (Google Cloud Build)
├── .gitignore                    # Sluit gevoelige/irrelevante bestanden uit
├── .dockerignore                 # Sluit bestanden uit van Docker-build
├── .env                          # Lokale ontwikkelomgeving variabelen
└── venv/                         # Virtuele Python-omgeving (niet committen)
```

---

## 🚀 Uitvoeren in Google Cloud Run Service

1. Ga naar **Google Cloud Console → Cloud Run → Services**  
2. Selecteer de service: **`service-webhook-cf`**
3. Stuur JSON-body incl. X-CF-Signature (Header) naar: https://service-webhook-cf-508826694512.europe-west1.run.app/webhook
{
  "StepName": "Asset Delivery",
  "ProductCode": "395808-GRS-MEL"
}

4. Testen via [web adk] of via http://localhost:8080/webhook

---

## 📊 Logs bekijken

Ga naar: **Cloud Run → Services → service-webhook-cf → Logs**  

Hier vind je:  
- AI output JSON  
- Geanalyseerde afbeeldingen  
- Eventuele foutmeldingen (zoals ontbrekende afbeeldingen of API errors)  

---

## 🔐 Geheimen beheren

- API-sleutels en andere gevoelige gegevens worden beheerd via **Google Secret Manager**.  
- Deze worden beschikbaar gemaakt via **environment variables** en automatisch opgehaald in `config.py`.  

---

## 👤 Auteur & Beheer

- Ontwikkeld voor **Ecom-Applicatiebeheer** als intern AI-project  
- Opgezet en beheerd door het **E-commerce Applicatiebeheer team**  

---

## 📄 Licentie

Private repository – uitsluitend bedoeld voor intern gebruik bij The Sting Companies.  
Niet bedoeld voor externe distributie of commercieel hergebruik.