## 🚀 Media Pipelines Demo

### 🎯 What is this about?
Single-day video pipeline on AWS that:
- Ingests Creative Commons videos from Wikimedia Commons and Pixabay
- Runs Amazon Rekognition for scene-level labels
- Stores structured metadata ready for editors or automation

Runs on schedule (EventBridge) with a Streamlit dashboard for manual control and monitoring.

**🔗 [Streamlit Dashboard](YOUR_STREAMLIT_URL_HERE)**

---

### 🧱 Building blocks (built in one day)
- **Orchestration**: AWS Step Functions (Map state for parallel processing, wait/choice for async jobs)
  - State machine: [`infrastructure/video_state_machine.asl.json`](infrastructure/video_state_machine.asl.json)
- **Compute**: AWS Lambda (Python 3.11)
- **Storage**: Amazon S3 (`media-raw/`, `media-processed/`)
- **Scheduling**: Amazon EventBridge (weekly cron)
- **UI & monitoring**: Streamlit dashboard (local or Streamlit Community Cloud)
- **Notifications**: optional Amazon SNS

**External sources**
- 🎬 Wikimedia Commons API and Pixabay API (Creative Commons video)

Chosen for legal, attribution-friendly assets without manual uploads.

---

### 🔄 Campaigns and triggers
- **Campaigns**: Themes like `travel`, `tech`, `nature` stored in S3/Parameter Store
- **Triggers**:
  - **Automatic**: EventBridge cron runs weekly
  - **Manual**: Streamlit dashboard (default batch size: 2 videos). Campaign persists for next scheduled run.

---

### 🎥 Video pipeline
1. **Ingest Lambda**: Searches Wikimedia Commons and Pixabay, distributes batch evenly, prevents duplicates (checks DynamoDB), uploads to `media-raw/video/<source>/<campaign>/<timestamp>/`

2. **Rekognition starter**: Launches one Rekognition job per video for label detection

3. **Map State**: Processes jobs in parallel (max 5), waits 30s between checks, polls until complete

4. **Finalize Lambda**: Retrieves labels/timestamps/moderation, saves to `media-processed/video/<source>/<campaign>/<timestamp>/labels.json` with summary

5. **Index Lambda**: Stores metadata in DynamoDB for dashboard queries

6. **Monitoring**: Streamlit shows execution logs, status, and statistics

---

### 📊 Streamlit dashboard
- **Manual triggers**: Campaign dropdown + batch size slider
- **Real-time monitoring**: Auto-refreshes during execution, shows Step Functions logs
- **Execution history**: Table with status, campaign, batch size, files processed, execution IDs
- **Statistics**: Raw/processed counts by source (Wikimedia/Pixabay)
- **Detailed logs**: Full Step Functions history (timestamps, durations, Lambda outputs, job IDs, S3 keys, labels)
- **Last execution summary**: Videos received/processed, expandable execution log

Auto-refreshes when running. Deploy via Streamlit Community Cloud, App Runner, or Fargate.

---

### 🪣 Data lake structure
```
media-raw/<type>/<source>/<campaign>/<YYYYMMDD>/<filename>
media-processed/<type>/<source>/<campaign>/<YYYYMMDD>/<summary>.json
```

Example:
```
media-raw/video/wikimedia/nature/20240115_120000/video1.mp4
media-raw/video/pixabay/nature/20240115_120000/video2.mp4
media-processed/video/wikimedia/nature/20240115_120000/video1_labels.json
media-processed/video/pixabay/nature/20240115_120000/video2_labels.json
```

Sources separated for traceability. DynamoDB indexes all processed artifacts for dashboard queries.

---

### ✅ Testing
- Unit tests (`pytest`) for API parsing and metadata calculations
- Smoke test script: triggers Step Functions (batch size 1), verifies S3 outputs

---

### 🔍 Code Quality
- **Ruff**: Linter/formatter (`pyproject.toml`)
- **Pre-commit hooks**: Auto-run linting, formatting, tests

---

### 🤔 Why this scope?
Single-day demo showcasing data engineering: ingestion, enrichment, orchestration, observability.

**Why small batch sizes?**
- Minimize personal AWS costs for demo
- Stay within public API rate limits (Wikimedia/Pixabay)
- Better visibility for debugging
- Demo-friendly output

Production-ready architecture—scale by increasing batch sizes and enabling parallel processing. Preselected campaigns ensure consistent output; architecture supports trend feeds and user-specific campaigns.

---

### 🔭 Potential next steps
- Automate campaign rotation (Pytrends/trends provider)
- Parallelize ingestion (Step Functions Map states)
- Expose APIs for downstream services (DynamoDB/OpenSearch)
- Deeper CV features (OpenCV shot detection, scene transitions)
- Aesthetic tagging (editing style, lighting, scenography, wardrobe)
- Full observability (CloudWatch dashboards, alarms, Slack alerts)
- Integration tests (LocalStack), CI/CD regression runs
