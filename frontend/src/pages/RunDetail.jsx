import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"

import Layout from "../components/Layout"

function formatDate(value) {
  if (!value) return "-"
  return new Date(value).toLocaleString()
}

export default function RunDetail() {
  const { runId } = useParams()
  const [run, setRun] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true

    async function loadRun() {
      try {
        const response = await fetch(`/api/registry/runs/${runId}`)
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Run not found")
        if (active) setRun(data)
      } catch (loadError) {
        if (active) setError(loadError.message)
      }
    }

    void loadRun()
    return () => {
      active = false
    }
  }, [runId])

  return (
    <Layout currentStep={null} contentClassName="max-w-5xl">
      <div className="space-y-6">
        <div>
          <Link to="/registry" className="text-sm text-zinc-400 hover:text-zinc-200">
            Back to registry
          </Link>
          <h1 className="mt-3 text-2xl font-semibold text-zinc-100">Run {runId}</h1>
        </div>

        {error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p> : null}

        {run ? (
          <>
            <section className="grid gap-3 sm:grid-cols-4">
              <Fact label="Type" value={run.run_type} />
              <Fact label="Status" value={run.status} />
              <Fact label="Duration" value={run.duration_seconds ? `${run.duration_seconds}s` : "-"} />
              <Fact label="Dataset" value={run.dataset_id || "-"} />
            </section>

            {run.diagnostics?.length ? (
              <section className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-4">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-amber-300">Diagnostics</h2>
                <div className="space-y-2">
                  {run.diagnostics.map((item) => (
                    <div key={item.code} className="rounded border border-amber-800/40 bg-zinc-950/40 p-3">
                      <p className="text-sm font-medium text-amber-200">{item.code}</p>
                      <p className="mt-1 text-sm text-zinc-300">{item.message}</p>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}

            <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">Timeline</h2>
              <div className="space-y-3">
                {(run.events || []).map((event) => (
                  <div key={event.event_id} className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <p className="font-mono text-xs text-brand-300">{event.event_type}</p>
                      <p className="text-xs text-zinc-500">{formatDate(event.created_at)}</p>
                    </div>
                    {event.message ? <p className="mt-2 text-sm text-zinc-300">{event.message}</p> : null}
                    {event.payload && Object.keys(event.payload).length > 0 ? (
                      <pre className="mt-3 max-h-48 overflow-auto rounded bg-zinc-950 p-3 text-xs text-zinc-400">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                ))}
                {run.events?.length === 0 ? <p className="text-sm text-zinc-500">No events recorded.</p> : null}
              </div>
            </section>

            <section className="grid gap-6 lg:grid-cols-2">
              <JsonPanel title="Config" value={run.config} />
              <JsonPanel title="Metrics" value={run.metrics} />
            </section>

            <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">Run Log</h2>
              {run.logs?.length ? (
                <pre className="max-h-96 overflow-auto rounded bg-zinc-950 p-3 text-xs leading-5 text-zinc-400">
                  {run.logs.join("\n")}
                </pre>
              ) : (
                <p className="text-sm text-zinc-500">No durable log lines recorded for this run.</p>
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
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 break-all text-sm font-medium text-zinc-100">{value}</p>
    </div>
  )
}

function JsonPanel({ title, value }) {
  return (
    <section className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-400">{title}</h2>
      <pre className="max-h-96 overflow-auto rounded bg-zinc-950 p-3 text-xs text-zinc-400">
        {JSON.stringify(value || {}, null, 2)}
      </pre>
    </section>
  )
}
