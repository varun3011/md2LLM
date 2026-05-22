# Task: Evolve md2LLM into an Observability and Management Layer for Fine-Tuned Models

## Objective

Extend `md2LLM` from a fine-tuning workflow app into a lightweight control plane for managing, evaluating, and observing fine-tuned models over time.

The current product already handles:

- markdown ingestion
- training data generation
- hardware-aware model selection
- local fine-tuning flows
- local chat through Ollama

The next phase should add the missing operational layer around those capabilities so users can answer:

- What datasets produced which models?
- Which training runs succeeded or failed?
- Which model version is currently the best?
- Did a new fine-tune improve quality or make it worse?
- What happened during training and after deployment?

## Current State

The existing codebase is strong on the pipeline itself but weak on persistent lifecycle management.

Relevant current behavior:

- generation jobs are tracked in memory via [server/state.py](/Users/csuftitan/Desktop/ownLLM/server/state.py:1)
- training metadata and progress are written as ad hoc files under `output/`
- models are discovered primarily from Ollama and local `.gguf` files in [server/routes/models.py](/Users/csuftitan/Desktop/ownLLM/server/routes/models.py:1)
- the product flow is documented as a staged pipeline in [README.md](/Users/csuftitan/Desktop/ownLLM/README.md:1) and [docs/architecture.md](/Users/csuftitan/Desktop/ownLLM/docs/architecture.md:1)

This means the app behaves like a workflow assistant, not yet like a durable model operations system.

## Problem Statement

The application lacks a durable system of record for datasets, runs, models, evaluations, and inference behavior.

Because of that, the following product capabilities are missing:

- reproducibility of training outcomes
- run history across restarts
- dataset lineage
- model version registry
- automatic evaluation after training
- comparison of runs or model versions
- operational monitoring for chat/inference usage
- alerting and failure diagnostics

## Product Direction

Reposition the app as a fine-tuning control plane with four core domains:

1. `Datasets`
2. `Training Runs`
3. `Models`
4. `Evaluation and Monitoring`

The product should keep the current pipeline UX, but add durable operational visibility on top of it.

## Scope of Work

### 1. Dataset Lineage and Versioning

Create a persistent dataset registry so each generated training dataset is versioned and traceable.

Each dataset record should include:

- dataset ID
- source type: vault, folder upload, zip upload, or imported JSONL
- source path or upload job reference
- generation goal: `knowledge`, `style`, `reasoning`, `chatbot`
- note selection stats
- quality threshold used
- generation model/provider used
- prompt template version
- file count included
- pair count produced
- output artifact path
- dataset content hash
- created timestamp

Expected outcome:

- every training run can reference an exact dataset version
- users can inspect how a dataset was produced
- future retraining becomes reproducible

### 2. Persistent Run Registry

Replace ephemeral in-memory job tracking with durable records stored in a database.

Run types should include:

- dataset generation runs
- training runs
- export runs
- evaluation runs

Each run record should include:

- run ID
- run type
- status: queued, running, succeeded, failed, cancelled
- start time
- end time
- duration
- dataset ID if applicable
- base model ID
- output model ID if applicable
- config snapshot
- machine or hardware summary
- log location
- error summary
- metrics summary

Expected outcome:

- job history survives restarts
- users can inspect past runs from the UI
- failures become diagnosable

### 3. Model Registry

Add a real model registry instead of only file discovery.

Each model record should include:

- model ID
- display name
- base model repo or source
- training run ID
- dataset ID
- artifact path
- format: adapter, merged model, gguf
- size
- created timestamp
- readiness status
- deployment status: draft, staging, production, archived
- tags such as `best`, `candidate`, `failed_eval`

Expected outcome:

- users can track model versions over time
- users can promote or archive models intentionally
- trained models are tied back to exact runs and datasets

### 4. Training Observability

Capture structured telemetry for active and historical training runs.

Metrics to capture:

- current epoch or step
- total steps
- loss
- learning rate
- elapsed time
- ETA
- checkpoint creation events
- hardware utilization summary if available
- warnings and failures

Frontend capabilities:

- live training progress view
- historical run detail page
- training logs and error panel
- simple charts for loss and step progress

Expected outcome:

- training is observable while running
- users can debug unhealthy or slow runs

### 5. Evaluation Pipeline

Add automatic post-training evaluation before a model is considered ready.

Evaluation types should include:

- benchmark prompt set
- knowledge recall checks
- style consistency checks
- reasoning quality checks
- hallucination review cases
- latency and throughput checks

Each evaluation record should include:

- evaluation ID
- model ID
- dataset ID
- evaluation suite version
- prompt set version
- aggregate score
- dimension-level scores
- notes or failure reasons
- created timestamp

Expected outcome:

- model quality is measured, not assumed
- users can compare fine-tunes objectively

### 6. Inference Monitoring

Track runtime behavior for chat or deployed usage.

Capture:

- request count
- latency
- error rate
- model used
- token usage if available
- user feedback or thumbs up/down
- flagged bad responses

Expected outcome:

- model quality can be monitored after training
- regressions can be detected in actual usage

### 7. Compare and Decision Views

Add comparison screens that help users decide what to keep or promote.

Comparisons should support:

- dataset A vs dataset B
- model A vs model B
- run A vs run B
- base model choice comparisons
- hyperparameter comparisons

Show side-by-side:

- config differences
- eval score differences
- training duration
- artifact size
- deployment status

Expected outcome:

- the app becomes useful for iteration, not just execution

## Suggested Architecture

### Backend

Add a persistent datastore for operational metadata.

Recommended first choice:

- `SQLite` for local single-user development

Tables to introduce:

- `datasets`
- `runs`
- `run_events`
- `models`
- `evaluations`
- `inference_logs`

Design rules:

- treat files under `output/` and `models/` as artifacts
- treat the database as the source of truth for metadata and relationships
- store append-only run events for progress and logs where possible

### Event Model

Introduce a structured event schema for long-running tasks.

Event types may include:

- `run.created`
- `run.started`
- `run.progress`
- `run.warning`
- `run.failed`
- `run.completed`
- `artifact.created`
- `evaluation.completed`

This should replace ad hoc progress handling with a consistent lifecycle model.

### Frontend

Add new pages or sections for:

- dataset history
- run history
- run detail
- model registry
- model detail
- evaluation detail
- compare view

The current workflow pages can remain, but they should write into the new persistent system.

## Recommended Implementation Order

### Phase 1: Foundation

- add database layer and schema
- implement dataset registry
- implement persistent run registry
- keep existing file artifacts unchanged for now

### Phase 2: Training Telemetry

- add structured run events
- stream training progress into durable storage
- add run detail UI with status, logs, and metrics

### Phase 3: Model Registry

- persist model records after training or import
- connect models to runs and datasets
- add deploy status and tags

### Phase 4: Evaluation

- add evaluation pipeline after training completion
- store evaluation scores and prompt-level results
- expose model comparison UI

### Phase 5: Inference Monitoring

- instrument chat requests
- capture latency, failures, and feedback
- surface post-training operational visibility

## Non-Goals for This Task

Do not expand scope into these areas yet:

- multi-tenant SaaS architecture
- cloud deployment orchestration
- distributed training management
- advanced RBAC or team permissions
- external observability vendor integrations

The first goal is a reliable local control plane, not an enterprise platform.

## Acceptance Criteria

The task is complete when:

- datasets are versioned and persisted
- all generation and training runs are durable across server restarts
- trained models are registered with lineage to dataset and run
- training logs and progress are viewable after completion
- at least one evaluation workflow runs automatically after training
- users can compare at least two model versions side by side
- chat usage produces basic inference telemetry

## Implementation Notes

- avoid building charts first without a clean metadata model
- do not keep critical state only in memory
- preserve current workflow routes where possible and migrate them gradually
- prefer incremental migration over a large rewrite
- keep artifact files on disk, but make metadata queryable and durable

## Deliverables

- database schema for operational metadata
- backend services for datasets, runs, models, evaluations, inference logs
- updated API routes for persistent lifecycle management
- frontend pages for history, detail, and comparison
- migration of current workflow pages to the new registry model
- documentation updates describing the new control-plane architecture

## Summary

The right next step is not more fine-tuning logic. The right next step is turning the existing pipeline into a system that can explain, compare, and manage what it produces.

That means:

- persistent lineage
- durable runs
- model registry
- evaluation
- observability

This will make `md2LLM` useful not only for creating a model once, but for operating model iteration as an ongoing workflow.
