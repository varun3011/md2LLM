import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"

import Layout from "../components/Layout"

const CONFIG = {
  models: {
    label: "Models",
    listUrl: "/api/registry/models",
    listKey: "models",
    idKey: "model_id",
    nameKey: "display_name",
    compareUrl: "/api/registry/compare/models",
  },
  datasets: {
    label: "Datasets",
    listUrl: "/api/registry/datasets",
    listKey: "datasets",
    idKey: "dataset_id",
    nameKey: "dataset_id",
    compareUrl: "/api/registry/compare/datasets",
  },
  runs: {
    label: "Runs",
    listUrl: "/api/registry/runs",
    listKey: "runs",
    idKey: "run_id",
    nameKey: "run_id",
    compareUrl: "/api/registry/compare/runs",
  },
}

export default function CompareModels() {
  const [kind, setKind] = useState("models")
  const [items, setItems] = useState([])
  const [left, setLeft] = useState("")
  const [right, setRight] = useState("")
  const [comparison, setComparison] = useState(null)
  const [error, setError] = useState("")

  const config = CONFIG[kind]

  useEffect(() => {
    let active = true

    async function loadItems() {
      try {
        setError("")
        setComparison(null)
        const response = await fetch(config.listUrl)
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || `Failed to load ${config.label.toLowerCase()}`)
        const nextItems = data[config.listKey] || []
        if (active) {
          setItems(nextItems)
          setLeft(nextItems[0]?.[config.idKey] || "")
          setRight(nextItems[1]?.[config.idKey] || nextItems[0]?.[config.idKey] || "")
        }
      } catch (loadError) {
        if (active) setError(loadError.message)
      }
    }

    void loadItems()
    return () => {
      active = false
    }
  }, [config.idKey, config.label, config.listKey, config.listUrl, kind])

  useEffect(() => {
    let active = true

    async function compare() {
      if (!left || !right) return
      try {
        setError("")
        const response = await fetch(
          `${config.compareUrl}?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`,
        )
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Comparison failed")
        if (active) setComparison(data)
      } catch (compareError) {
        if (active) setError(compareError.message)
      }
    }

    void compare()
    return () => {
      active = false
    }
  }, [config.compareUrl, left, right])

  const fields = useMemo(() => Object.entries(comparison?.differences || {}), [comparison])

  return (
    <Layout currentStep={null} contentClassName="max-w-5xl">
      <div className="space-y-6">
        <div>
          <Link to="/registry" className="text-sm text-zinc-400 hover:text-zinc-200">
            Back to registry
          </Link>
          <h1 className="mt-3 text-2xl font-semibold text-zinc-100">Compare</h1>
          <p className="mt-2 text-sm text-zinc-400">
            Compare model versions, dataset lineage, or run configurations side by side.
          </p>
        </div>

        {error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p> : null}

        <section className="space-y-4 rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
          <div className="flex flex-wrap gap-2">
            {Object.entries(CONFIG).map(([value, entry]) => (
              <button
                key={value}
                type="button"
                onClick={() => setKind(value)}
                className={[
                  "rounded-lg border px-3 py-1.5 text-sm",
                  kind === value
                    ? "border-brand-500 bg-brand-600/20 text-brand-200"
                    : "border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700",
                ].join(" ")}
              >
                {entry.label}
              </button>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <ItemSelect label={`Left ${config.label.toLowerCase()}`} config={config} items={items} value={left} onChange={setLeft} />
            <ItemSelect label={`Right ${config.label.toLowerCase()}`} config={config} items={items} value={right} onChange={setRight} />
          </div>
        </section>

        {items.length < 2 ? (
          <p className="rounded-lg border border-zinc-700 bg-zinc-900 p-4 text-sm text-zinc-400">
            At least two {config.label.toLowerCase()} are needed for a useful comparison.
          </p>
        ) : null}

        {comparison ? (
          <section className="overflow-x-auto rounded-lg border border-zinc-700/50 bg-zinc-900 p-4">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="border-b border-zinc-800 px-3 py-2">Field</th>
                  <th className="border-b border-zinc-800 px-3 py-2">{labelFor(comparison.left, config)}</th>
                  <th className="border-b border-zinc-800 px-3 py-2">{labelFor(comparison.right, config)}</th>
                  <th className="border-b border-zinc-800 px-3 py-2">Same</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800 text-zinc-300">
                {fields.map(([field, diff]) => (
                  <tr key={field}>
                    <td className="px-3 py-2 font-medium text-zinc-200">{field}</td>
                    <td className="break-all px-3 py-2">{formatValue(diff.left)}</td>
                    <td className="break-all px-3 py-2">{formatValue(diff.right)}</td>
                    <td className={diff.same ? "px-3 py-2 text-emerald-300" : "px-3 py-2 text-amber-300"}>
                      {diff.same ? "yes" : "no"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}
      </div>
    </Layout>
  )
}

function ItemSelect({ label, config, items, value, onChange }) {
  return (
    <label className="space-y-2">
      <span className="text-xs uppercase tracking-wide text-zinc-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
      >
        {items.map((item) => (
          <option key={item[config.idKey]} value={item[config.idKey]}>
            {labelFor(item, config)}
          </option>
        ))}
      </select>
    </label>
  )
}

function labelFor(item, config) {
  return item?.[config.nameKey] || item?.[config.idKey] || "-"
}

function formatValue(value) {
  if (Array.isArray(value)) return value.join(", ") || "-"
  if (value === null || value === undefined || value === "") return "-"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}
