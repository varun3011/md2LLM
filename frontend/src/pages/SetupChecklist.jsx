import { useEffect, useState } from "react"

import Layout from "../components/Layout"

const CHECKS = [
  ["backend_running", "Backend running"],
  ["frontend_running", "Frontend running"],
  ["ollama_running", "Ollama running"],
  ["models_found", "Models found"],
  ["training_data_exists", "Training data exists"],
]

export default function SetupChecklist() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true

    async function loadStatus() {
      try {
        const response = await fetch("/api/setup/status")
        if (!response.ok) {
          throw new Error("Failed to load setup status")
        }
        const data = await response.json()
        if (active) setStatus(data)
      } catch (statusError) {
        if (active) setError(statusError.message)
      }
    }

    void loadStatus()
    return () => {
      active = false
    }
  }, [])

  return (
    <Layout currentStep={null} contentClassName="max-w-3xl">
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Setup Checklist</h1>
          <p className="mt-2 text-sm text-zinc-400">
            Current local app status for first-time setup.
          </p>
        </div>

        {error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p> : null}

        <section className="overflow-hidden rounded-lg border border-zinc-700/50 bg-zinc-900">
          {CHECKS.map(([key, label]) => (
            <CheckRow key={key} label={label} value={status?.[key]} loading={!status && !error} />
          ))}
        </section>

        {status ? (
          <section className="grid gap-3 sm:grid-cols-2">
            <CountCard label="Models detected" value={status.model_count} />
            <CountCard label="Training data files" value={status.training_data_files} />
          </section>
        ) : null}
      </div>
    </Layout>
  )
}

function CheckRow({ label, value, loading }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3 last:border-b-0">
      <span className="text-sm font-medium text-zinc-200">{label}</span>
      <StatusBadge value={value} loading={loading} />
    </div>
  )
}

function StatusBadge({ value, loading }) {
  if (loading) {
    return <span className="rounded-full border border-zinc-700 bg-zinc-800 px-3 py-1 text-xs text-zinc-400">Checking</span>
  }

  const ok = Boolean(value)
  const className = ok
    ? "border-emerald-700/50 bg-emerald-900/20 text-emerald-300"
    : "border-red-700/50 bg-red-900/20 text-red-300"

  return <span className={`rounded-full border px-3 py-1 text-xs font-medium ${className}`}>{ok ? "Yes" : "No"}</span>
}

function CountCard({ label, value }) {
  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-zinc-100">{value ?? 0}</p>
    </div>
  )
}
