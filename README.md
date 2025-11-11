## 🚀 Media Pipelines Demo

### 🎯 What is this about?
A single-day sprint that wires up a practical video pipeline on AWS:
- **Video pipeline** pulls Creative Commons clips and runs computer vision so each file comes with scene-level labels ready for an editor or automation agent.

The pipeline runs on a schedule, and a tiny Streamlit dashboard lets anyone fire it manually, tweak parameters, and inspect what landed in the data lake.

---

### 🧱 Building blocks (built in one day)
- **Orchestration**: AWS Step Functions (wait/choice for async jobs)
- **Compute**: AWS Lambda (Python 3.11)
- **Storage**: Amazon S3 (`media-raw/`, `media-processed/`)
- **Scheduling**: Amazon EventBridge (weekly cron)
- **UI & monitoring**: Streamlit dashboard (local or Streamlit Community Cloud)
- **Notifications**: optional Amazon SNS

**External sources**
- 🎬 Wikimedia Commons API and Pixabay API for Creative Commons video

APIs were selected because they ship legal, attribution-friendly assets without manual uploads, keeping the MVP realistic and fast to deliver.

---

### 🔄 Campaigns and triggers
- **Campaigns**: a curated list of themes (e.g. `travel`, `tech`, `nature`) stored in S3 or Parameter Store so we always get results; documentation explains how to swap in automatic trend feeds later.
- **Triggers**:
  - Automatic (EventBridge cron) reads the active campaign and batch sizes, then kicks off the pipeline.
  - Manual (Streamlit dashboard) lets you change the campaign, adjust batch sizes (default 2 video), and run the pipeline instantly. The chosen campaign persists so the next scheduled run uses it too.

---

### 🎥 Video pipeline (computer vision enrichment)
1. **Ingest Lambda**
   - Reads campaign and `batch_size_video`.
   - Searches Wikimedia Commons for Creative Commons clips matching the theme; if none appear we can fall back to other APIs.
   - Uploads files to `media-raw/video/<campaign>/<timestamp>/`.

2. **Rekognition starter**
   - Launches Amazon Rekognition Video for label detection and optional moderation.

3. **Step Functions wait loop**
   - Polls Rekognition until the job completes.

4. **Finalize Lambda**
   - Retrieves labels, timestamps, scene segments, and moderation flags.
   - Normalizes everything into `media-processed/video/<campaign>/<timestamp>/labels.json` with a friendly summary.

5. **Monitoring**
   - Streamlit shows processed clips, highlights top labels, and records execution status.

---

### 📊 Streamlit dashboard
- Campaign dropdown (persists to S3 or Parameter Store)
- Slider for video batch size
- Button for manual runs
- Table of recent executions (status, campaign, batch size, timestamps)
- Counters of raw vs processed assets per campaign
- Peek into the latest JSON summaries

Streamlit Community Cloud is the fastest way to share it; App Runner or Fargate are AWS-native alternatives.

---

### 🪣 Data lake view
- Folder pattern (following data engineering best practices - sources separated):
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
- Sources are kept separated for better traceability, compliance, and independent analysis.
- Lightweight index file or DynamoDB table captures every processed artifact so the dashboard can show history and totals.

---

### ✅ Testing in scope (built during the day)
- Unit tests for utility functions (API response parsing, metadata calculations) using `pytest`.
- A smoke test script that triggers each Step Function with batch size 1 and checks S3 for new outputs. Intended to run before demo/hand-off.

---

### 🔍 Code Quality & Linting
- **Ruff**: Fast Python linter and formatter (configured in `pyproject.toml`).
- **Pre-commit hooks**: Automatically run linting, formatting, and tests before every commit.

---

### 🤔 Why this scope?
- Covers the core responsibilities of a data pipeline: ingestion from external APIs, enrichment, orchestration, and observability.
- Fits in a single day while still showcasing modern AWS patterns and clean documentation.
- Campaigns are preselected so the demo always produces meaningful output, yet the architecture already expects more advanced inputs (trend feeds, user-specific campaigns) later.
- Batch sizes are configurable per run. Defaults stay small for the MVP, but the design is ready for larger volumes as soon as we flip the switch.

---

### 🔭 What's next after the MVP?
- Automate campaign rotation via Pytrends or another trends provider.
- Parallelize ingestion with Step Functions Map states for high-volume runs.
- Persist metadata in DynamoDB or OpenSearch and expose APIs to downstream services.
- Add deeper CV features (OpenCV shot detection, scene transitions).
- Extend computer vision to tag aesthetic and production cues (editing style, acting style, lighting treatment, scenography, wardrobe, etc.).
- Build fuller observability (CloudWatch dashboards, alarms, Slack alerts).
- Expand automated test coverage: integration tests with LocalStack, end-to-end regression runs triggered in CI.
