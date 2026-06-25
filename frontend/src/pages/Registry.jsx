import { useEffect, useState } from "react"
import { Link } from "react-router-dom"

import Layout from "../components/Layout"

function formatDate(value) {
  if (!value) return "-"
  return new Date(value).toLocaleString()
}

function StatusBadge({ value }) {
  const color =
    value === "succeeded" || value === "ready"
      ? "border-emerald-700/50 bg-emerald-900/20 text-emerald-300"
      : value === "failed"
        ? "border-red-700/50 bg-red-900/20 text-red-300"
        : value === "running"
          ? "border-blue-700/50 bg-blue-900/20 text-blue-300"
          : "border-zinc-700 bg-zinc-800 text-zinc-300"
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs ${color}`}>
      {value || "unknown"}
    </span>
  )
}

export default function Registry() {
  const [summary, setSummary] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [runs, setRuns] = useState([])
  const [models, setModels] = useState([])
  const [evaluations, setEvaluations] = useState([])
  const [inferenceLogs, setInferenceLogs] = useState([])
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true

    async function loadRegistry() {
      try {
        const [summaryRes, datasetsRes, runsRes, modelsRes, evalsRes, inferenceRes] =
          await Promise.all([
            fetch("/api/registry/summary"),
            fetch("/api/registry/datasets"),
            fetch("/api/registry/runs"),
            fetch("/api/registry/models"),
            fetch("/api/registry/evaluations"),
            fetch("/api/registry/inference-logs"),
          ])

        for (const response of [summaryRes, datasetsRes, runsRes, modelsRes, evalsRes, inferenceRes]) {
          if (!response.ok) throw new Error("Failed to load registry data")
        }

        const [summaryData, datasetsData, runsData, modelsData, evalsData, inferenceData] =
          await Promise.all([
            summaryRes.json(),
            datasetsRes.json(),
            runsRes.json(),
            modelsRes.json(),
            evalsRes.json(),
            inferenceRes.json(),
          ])

        if (active) {
          setSummary(summaryData)
          setDatasets(datasetsData.datasets || [])
          setRuns(runsData.runs || [])
          setModels(modelsData.models || [])
          setEvaluations(evalsData.evaluations || [])
          setInferenceLogs(inferenceData.inference_logs || [])
        }
      } catch (loadError) {
        if (active) setError(loadError.message)
      }
    }

    void loadRegistry()
    return () => {
      active = false
    }
  }, [])

  return (
    <Layout currentStep={null} contentClassName="max-w-6xl">
      <div className="space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Registry</h1>
            <p className="mt-2 text-sm text-zinc-400">
              Persistent datasets, runs, models, evaluations, and inference telemetry.
            </p>
          </div>
          <Link
            to="/compare"
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-700"
          >
            Compare models
          </Link>
        </div>

        {error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p> : null}

        <section className="grid gap-3 sm:grid-cols-5">
          {["datasets", "runs", "models", "evaluations", "inference_logs"].map((key) => (
            <div key={key} className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
              <p className="text-xs uppercase tracking-wide text-zinc-500">{key.replace("_", " ")}</p>
              <p className="mt-2 text-2xl font-semibold text-zinc-100">{summary?.counts?.[key] ?? 0}</p>
            </div>
          ))}
        </section>

        <Section title="Runs">
          <Table
            headers={["Run", "Type", "Status", "Dataset", "Updated"]}
            empty="No runs recorded yet."
            rows={runs.map((run) => [
              <Link className="font-mono text-brand-300 hover:text-brand-200" to={`/runs/${run.run_id}`}>
                {run.run_id}
              </Link>,
              run.run_type,
              <StatusBadge value={run.status} />,
              run.dataset_id || "-",
              formatDate(run.updated_at),
            ])}
          />
        </Section>

        <Section title="Datasets">
          <Table
            headers={["Dataset", "Source", "Goal", "Pairs", "Artifact"]}
            empty="No datasets recorded yet."
            rows={datasets.map((dataset) => [
              <span className="font-mono text-zinc-200">{dataset.dataset_id}</span>,
              dataset.source_type,
              dataset.generation_goal || "-",
              dataset.pair_count,
              <span className="break-all text-xs text-zinc-400">{dataset.artifact_path || "-"}</span>,
            ])}
          />
        </Section>

        <Section title="Models">
          <Table
            headers={["Model", "Base", "Status", "Deployment", "Dataset"]}
            empty="No models recorded yet. Visit Chat or finish training to populate this."
            rows={models.map((model) => [
              <Link className="font-medium text-brand-300 hover:text-brand-200" to={`/models/${model.model_id}`}>
                {model.display_name}
              </Link>,
              model.base_model_repo || "-",
              <StatusBadge value={model.readiness_status} />,
              model.deployment_status,
              model.dataset_id || "-",
            ])}
          />
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Evaluations">
            <Table
              headers={["Evaluation", "Model", "Score", "Created"]}
              empty="No evaluations recorded yet."
              rows={evaluations.map((evaluation) => [
                <span className="font-mono text-xs text-zinc-300">{evaluation.evaluation_id}</span>,
                evaluation.model_id,
                evaluation.aggregate_score ?? "-",
                formatDate(evaluation.created_at),
              ])}
            />
          </Section>

          <Section title="Inference Logs">
            <Table
              headers={["Model", "Success", "Latency", "Created"]}
              empty="No chat telemetry recorded yet."
              rows={inferenceLogs.map((log) => [
                log.model_name,
                log.success ? "yes" : "no",
                `${Math.round(log.latency_ms || 0)} ms`,
                formatDate(log.created_at),
              ])}
            />
          </Section>
        </div>
      </div>
    </Layout>
  )
}

function Section({ title, children }) {
  return (
    <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">{title}</h2>
      {children}
    </section>
  )
}

function Table({ headers, rows, empty }) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">{empty}</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            {headers.map((header) => (
              <th key={header} className="border-b border-zinc-800 px-3 py-2 font-medium">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800 text-zinc-300">
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
