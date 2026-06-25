import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"

import Layout from "../components/Layout"

function formatDate(value) {
  if (!value) return "-"
  return new Date(value).toLocaleString()
}

export default function ModelDetail() {
  const { modelId } = useParams()
  const [model, setModel] = useState(null)
  const [error, setError] = useState("")
  const [evaluating, setEvaluating] = useState(false)
  const [savingStatus, setSavingStatus] = useState(false)

  async function loadModel() {
    const response = await fetch(`/api/registry/models/${modelId}`)
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || "Model not found")
    setModel(data)
  }

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const response = await fetch(`/api/registry/models/${modelId}`)
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Model not found")
        if (active) setModel(data)
      } catch (loadError) {
        if (active) setError(loadError.message)
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [modelId])

  async function runEvaluation() {
    setEvaluating(true)
    setError("")
    try {
      const response = await fetch(`/api/registry/models/${modelId}/evaluate`, {
        method: "POST",
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Evaluation failed")
      await loadModel()
    } catch (evalError) {
      setError(evalError.message)
    } finally {
      setEvaluating(false)
    }
  }

  async function updateStatus(event) {
    event.preventDefault()
    if (!model) return
    setSavingStatus(true)
    setError("")

    const form = new FormData(event.currentTarget)
    try {
      const response = await fetch(`/api/registry/models/${modelId}/status`, {
        method: "POST",
        body: form,
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || "Failed to update model status")
      await loadModel()
    } catch (statusError) {
      setError(statusError.message)
    } finally {
      setSavingStatus(false)
    }
  }

  return (
    <Layout currentStep={null} contentClassName="max-w-5xl">
      <div className="space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <Link to="/registry" className="text-sm text-zinc-400 hover:text-zinc-200">
              Back to registry
            </Link>
            <h1 className="mt-3 text-2xl font-semibold text-zinc-100">
              {model?.display_name || modelId}
            </h1>
            <p className="mt-2 text-sm text-zinc-400">Model lineage, artifact metadata, and evaluation history.</p>
          </div>
          <button
            type="button"
            onClick={runEvaluation}
            disabled={evaluating || !model}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {evaluating ? "Evaluating..." : "Run evaluation"}
          </button>
        </div>

        {error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p> : null}

        {model ? (
          <>
            <section className="grid gap-3 sm:grid-cols-4">
              <Fact label="Status" value={model.readiness_status} />
              <Fact label="Deployment" value={model.deployment_status} />
              <Fact label="Format" value={model.format} />
              <Fact label="Size" value={model.size_bytes ? `${Math.round(model.size_bytes / 1024 / 1024)} MB` : "-"} />
            </section>

            <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">Lineage</h2>
              <div className="grid gap-3 sm:grid-cols-3">
                <Fact label="Dataset" value={model.dataset_id || "-"} />
                <Fact label="Training run" value={model.training_run_id || "-"} />
                <Fact label="Base model" value={model.base_model_repo || "-"} />
              </div>
              <p className="mt-4 break-all text-xs text-zinc-500">{model.artifact_path || "No artifact path recorded"}</p>
            </section>

            <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">Management</h2>
              <form onSubmit={updateStatus} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
                <label className="space-y-2">
                  <span className="text-xs uppercase tracking-wide text-zinc-500">Deployment</span>
                  <select
                    name="deployment_status"
                    defaultValue={model.deployment_status}
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                  >
                    {["draft", "staging", "production", "archived"].map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="text-xs uppercase tracking-wide text-zinc-500">Tags</span>
                  <input
                    name="tags"
                    defaultValue={(model.tags || []).join(", ")}
                    placeholder="best, candidate"
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100"
                  />
                </label>
                <button
                  type="submit"
                  disabled={savingStatus}
                  className="self-end rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
                >
                  {savingStatus ? "Saving..." : "Save"}
                </button>
              </form>
            </section>

            <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">Evaluations</h2>
              {model.evaluations?.length ? (
                <div className="space-y-4">
                  {model.evaluations.map((evaluation) => (
                    <EvaluationCard key={evaluation.evaluation_id} evaluation={evaluation} />
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-500">No evaluations recorded for this model yet.</p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </Layout>
  )
}

function Fact({ label, value }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 break-all text-sm font-medium text-zinc-100">{value || "-"}</p>
    </div>
  )
}

function EvaluationCard({ evaluation }) {
  const prompts = evaluation.scores?.prompts || []
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-xs text-brand-300">{evaluation.evaluation_id}</p>
          <p className="mt-1 text-sm text-zinc-400">{evaluation.notes}</p>
        </div>
        <div className="text-left sm:text-right">
          <p className="text-2xl font-semibold text-zinc-100">{evaluation.aggregate_score ?? "-"}</p>
          <p className="text-xs text-zinc-500">{formatDate(evaluation.created_at)}</p>
        </div>
      </div>
      {evaluation.scores?.dimensions ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-5">
          {Object.entries(evaluation.scores.dimensions).map(([dimension, score]) => (
            <div key={dimension} className="rounded border border-zinc-800 bg-zinc-900 p-2">
              <p className="truncate text-xs text-zinc-500">{dimension.replace("_", " ")}</p>
              <p className="mt-1 text-sm font-medium text-zinc-200">{score}</p>
            </div>
          ))}
        </div>
      ) : null}
      {prompts.length ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-zinc-400">Prompt results</summary>
          <div className="mt-3 space-y-2">
            {prompts.map((prompt) => (
              <div key={prompt.prompt_id} className="rounded border border-zinc-800 bg-zinc-900 p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-zinc-200">{prompt.dimension}</p>
                  <p className="text-xs text-zinc-500">
                    score {prompt.score} · {Math.round(prompt.latency_ms || 0)} ms
                  </p>
                </div>
                {prompt.error ? <p className="mt-2 text-xs text-red-300">{prompt.error}</p> : null}
                {prompt.response_preview ? (
                  <p className="mt-2 text-xs leading-5 text-zinc-400">{prompt.response_preview}</p>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  )
}
