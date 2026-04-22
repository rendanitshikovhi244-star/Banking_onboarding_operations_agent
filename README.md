# Banking Onboarding / KYC Multi-Agent System

A customer onboarding and KYC (Know Your Customer) pipeline built with **Google ADK** (Agent Development Kit), **HuggingFace** LLMs via LiteLLM, **Redis** for audit logging and compliance queuing, and deterministic rule-based screening tools.

---

## Architecture

```
OnboardingPipeline (Custom Sequential + Parallel Orchestration)
 ├── IntakeAgent              — normalises raw input (JSON or free-text) → CustomerIntake
 ├── DocumentAgent            — identifies required KYC docs per account type, flags gaps
 ├── ComplianceCheck (Parallel)
 │    ├── IdentityAgent       — cross-checks identity details, flags field mismatches
 │    └── AMLAgent            — PEP check, sanctions screening, adverse media, AML risk score
 ├── RiskAgent                — overall customer risk score, routing decision
 └── AuditAgent               — compiles OnboardingDecision, writes full audit trail to Redis
```

### Session State Keys (Inter-Agent Handoff)
| Key | Written By | Read By |
|---|---|---|
| `normalized_application` | IntakeAgent | All subsequent agents |
| `document_check` | DocumentAgent | RiskAgent, AuditAgent |
| `identity_verification` | IdentityAgent | RiskAgent, AuditAgent |
| `aml_screening` | AMLAgent | RiskAgent, AuditAgent |
| `risk_assessment` | RiskAgent | AuditAgent |
| `final_decision` | AuditAgent | API / CLI consumer |

### Redis Keys
| Key | Type | Purpose |
|---|---|---|
| `audit:{application_id}` | List | Per-agent audit entries (append-only, chronological) |
| `compliance_review_queue` | List | High-risk applications awaiting compliance officer review |

### Onboarding Decision Status Flow
```
pending_documents  ← missing required KYC documents
      ↓
identity_mismatch  ← name / DOB / address discrepancy detected
      ↓
aml_flagged        ← PEP, sanctions, or adverse media hit
      ↓
compliance_escalated ← high/critical risk score, requires EDD
      ↓
approved / rejected
```

---

## Project Structure

```
Banking_onboarding_operations_agent/
├── main.py                         CLI runner
├── api.py                          FastAPI endpoints
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── banking_agent/
│   ├── __init__.py
│   ├── agent.py                    BankingOnboardingAgent orchestrator
│   ├── .env                        secrets (git-ignored)
│   ├── configs/
│   │   ├── agent_configs.py        central registry of model + instructions
│   │   ├── logging_config.py       shared logger + before_agent_callback
│   │   └── model_config.py         MODEL_FAST / MODEL_MID / MODEL_MAIN
│   ├── schemas/
│   │   └── models.py               Pydantic schemas for all pipeline stages
│   ├── sessions/
│   │   └── redis_session_service.py  Redis-backed ADK session service
│   ├── sub_agents/
│   │   ├── intake_agent.py
│   │   ├── document_agent.py
│   │   ├── identity_agent.py
│   │   ├── aml_agent.py
│   │   ├── risk_agent.py
│   │   ├── audit_agent.py
│   │   └── conversational_agent.py  front-door OnboardingAssistant
│   └── tools/
│       ├── document_tools.py        KYC document requirement rules
│       ├── identity_tools.py        identity verification + mismatch detection
│       ├── aml_tools.py             AML / PEP / sanctions screening (simulated)
│       ├── redis_tools.py           audit log + compliance queue writes/reads
│       └── pipeline_runner_tool.py  submit_application, resubmit_with_documents
├── sample_applications/
│   ├── application_individual_001.json   standard individual, all docs present
│   ├── application_business_002.json     business account, missing docs
│   └── application_highrisk_003.json     high-risk: PEP flag + expired ID
├── logs/
└── tests/
    └── test_pipeline.py
```

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- Redis running locally (`redis-server` or Docker)
- A HuggingFace API key **or** a Google Gemini API key

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example banking_agent/.env
# Edit banking_agent/.env with your API keys
```

### 4. Run the CLI
```bash
# Process a sample application
python main.py sample_applications/application_individual_001.json

# Process a business application
python main.py sample_applications/application_business_002.json

# Process a high-risk application
python main.py sample_applications/application_highrisk_003.json

# Free-text input
python main.py "I'd like to open a personal savings account. My name is John Smith, DOB 1990-05-20..."
```

### 5. Run the API Server
```bash
uvicorn api:app --reload
# Visit http://localhost:8000/docs for Swagger UI
```

### 6. Run the ADK Web UI
```bash
adk web
# Launches the OnboardingAssistant conversational interface
```

### 7. Run Tests
```bash
pytest tests/ -v
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness + Redis connectivity |
| `POST` | `/applications` | Submit application through KYC pipeline |
| `GET` | `/applications/{id}/audit` | Fetch ordered audit trail |
| `GET` | `/compliance-queue` | Inspect compliance escalation queue |

### Example: Submit an Application
```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Jane Smith",
    "date_of_birth": "1985-06-15",
    "nationality": "US",
    "country_of_residence": "US",
    "id_type": "passport",
    "id_number": "P12345678",
    "id_expiry_date": "2030-01-01",
    "address": "123 Main St, New York, NY 10001",
    "phone_number": "+1-212-555-0100",
    "email": "jane@email.com",
    "account_type": "personal_checking",
    "source_of_funds": "employment",
    "employment_status": "employed",
    "annual_income": 75000,
    "documents_provided": ["government_id", "proof_of_address", "proof_of_income"]
  }'
```

### Example: Fetch Audit Trail
```bash
curl http://localhost:8000/applications/APP-20260422-001A/audit
```

---

## KYC Document Requirements

| Account Type | Required Documents |
|---|---|
| `personal_checking` | government_id, proof_of_address, proof_of_income |
| `personal_savings` | government_id, proof_of_address |
| `business_current` | company_registration, certificate_of_incorporation, proof_of_business_address, director_ids, ubo_declaration, bank_statements_6months |
| `business_savings` | company_registration, certificate_of_incorporation, proof_of_business_address, director_ids, ubo_declaration |
| `investment` | government_id, proof_of_address, proof_of_income, source_of_funds_declaration, tax_identification_number |

---

## Risk Routing Logic

| Risk Score | Risk Level | Routing Decision |
|---|---|---|
| 0.0 – 0.29 | low | `auto_approve` |
| 0.30 – 0.49 | medium | `standard_review` |
| 0.50 – 0.74 | high | `enhanced_due_diligence` |
| 0.75 – 0.89 | critical | `compliance_escalation` |
| 0.90 – 1.00 | critical | `reject` |

### Risk Factors Evaluated
- **Document completeness** — missing required KYC documents
- **Identity verification** — mismatches between application fields and ID documents
- **AML screening** — PEP status, sanctions list hits, adverse media
- **ID validity** — expired or near-expiry identity documents
- **Geographic risk** — high-risk jurisdictions (FATF grey/black list countries)
- **Source of funds** — unexplained wealth, cash-heavy industries
- **Income vs. account type** — investment accounts with low declared income

---

## Model Tier Assignments

| Model Tier | Agents | Rationale |
|---|---|---|
| `MODEL_FAST` | IntakeAgent, DocumentAgent | Structured JSON extraction, rule-based document mapping |
| `MODEL_MID` | IdentityAgent, AMLAgent, AuditAgent | Pattern matching, mismatch detection, summary writing |
| `MODEL_MAIN` | RiskAgent, OnboardingAssistant | Nuanced multi-factor reasoning, conversational interaction |

---

## Inspecting Results with Redis CLI

```bash
# View the full audit trail for an application
redis-cli LRANGE audit:APP-20260422-001A 0 -1

# Inspect the compliance escalation queue
redis-cli LRANGE compliance_review_queue 0 -1

# Count pending compliance reviews
redis-cli LLEN compliance_review_queue
```
