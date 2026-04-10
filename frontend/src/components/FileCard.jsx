import { useState } from "react"

function qualityBarClass(score) {
  if (score >= 0.8) {
    return "bg-green-500"
  }
  if (score >= 0.6) {
    return "bg-yellow-500"
  }
  return "bg-orange-500"
}

export default function FileCard({
  title,
  quality_score,
  word_count,
  tags,
  wikilinks,
  body_preview,
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <button
      type="button"
      onClick={() => setExpanded((value) => !value)}
      className="w-full rounded-xl border border-zinc-700/50 bg-zinc-900 p-5 text-left transition-all duration-150 hover:border-zinc-500 hover:bg-zinc-800/80"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">{title}</h3>
          <p className="mt-1 text-xs text-zinc-500">{word_count} words</p>
        </div>
        <span className="rounded-full border border-zinc-700/50 px-2 py-1 font-mono text-xs text-zinc-400">
          {quality_score.toFixed(2)}
        </span>
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between text-xs text-zinc-500">
          <span>Quality score</span>
          <span>{Math.round(quality_score * 100)}%</span>
        </div>
        <div className="h-2 rounded-full bg-zinc-800">
          <div
            className={`h-2 rounded-full transition-all duration-500 ease-out ${qualityBarClass(quality_score)}`}
            style={{ width: `${Math.max(8, quality_score * 100)}%` }}
          />
        </div>
      </div>

      <div className="mt-4 space-y-2 text-xs text-zinc-400">
        <div className="flex flex-wrap gap-2">
          {tags.length > 0 ? (
            tags.map((tag) => (
              <span key={tag} className="rounded-full bg-zinc-800 px-2 py-1 text-zinc-300">
                #{tag}
              </span>
            ))
          ) : (
            <span className="text-zinc-600">No tags</span>
          )}
        </div>

        <p className="truncate text-zinc-500">
          {wikilinks.length > 0 ? `Links: ${wikilinks.join(", ")}` : "No wiki links"}
        </p>

        {expanded && body_preview ? (
          <p className="rounded-lg border border-zinc-700/50 bg-zinc-950/60 p-3 text-sm leading-6 text-zinc-300">
            {body_preview}
          </p>
        ) : null}
      </div>
    </button>
  )
}
