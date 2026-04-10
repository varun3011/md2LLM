import { useEffect, useMemo, useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"

import { useMd2LLM } from "../App"
import Layout from "../components/Layout"

const qualityFilters = [
  { label: "All quality", value: "all" },
  { label: "0.8+", value: "high" },
  { label: "0.6+", value: "medium" },
  { label: "0.4+", value: "low" },
]

function qualityTone(score) {
  if (score >= 0.8) {
    return "bg-emerald-500"
  }
  if (score >= 0.6) {
    return "bg-amber-500"
  }
  return "bg-orange-500"
}

function qualityLabel(score) {
  if (score >= 0.8) {
    return "High confidence"
  }
  if (score >= 0.6) {
    return "Usable"
  }
  return "Borderline"
}

function formatPath(notePath) {
  const normalized = notePath.replace(/\\/g, "/")
  const marker = "/vault/"
  const index = normalized.lastIndexOf(marker)
  return index >= 0 ? normalized.slice(index + marker.length) : normalized.split("/").slice(-3).join("/")
}

function formatDirectory(notePath) {
  const relativePath = formatPath(notePath)
  const parts = relativePath.split("/")
  return parts.length > 1 ? parts.slice(0, -1).join("/") : "vault"
}

export default function ReviewFiles() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [search, setSearch] = useState("")
  const [qualityFilter, setQualityFilter] = useState("all")
  const [sortBy, setSortBy] = useState("score")
  const [selectedPath, setSelectedPath] = useState("")
  const {
    jobId,
    goal,
    notes,
    setNotes,
    vaultStats,
    setVaultStats,
    setCurrentStep,
  } = useMd2LLM()

  useEffect(() => {
    setCurrentStep(3)
  }, [setCurrentStep])

  useEffect(() => {
    if (!jobId) {
      return
    }

    let active = true

    async function scanVault() {
      setLoading(true)
      setError("")

      try {
        const formData = new FormData()
        formData.append("job_id", jobId)
        formData.append("min_quality", "0.4")

        const response = await fetch("/api/scan", {
          method: "POST",
          body: formData,
        })

        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          throw new Error(data.detail || "Vault scan failed")
        }

        const data = await response.json()
        if (active) {
          setNotes(data.notes)
          setVaultStats(data.stats)
        }
      } catch (scanError) {
        if (active) {
          setError(scanError.message)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    scanVault()
    return () => {
      active = false
    }
  }, [jobId, setNotes, setVaultStats])

  const filteredNotes = useMemo(() => {
    const searchTerm = search.trim().toLowerCase()
    const filtered = notes.filter((note) => {
      const matchesSearch =
        !searchTerm ||
        note.title.toLowerCase().includes(searchTerm) ||
        note.tags.join(" ").toLowerCase().includes(searchTerm) ||
        note.wikilinks.join(" ").toLowerCase().includes(searchTerm)

      if (!matchesSearch) {
        return false
      }

      if (qualityFilter === "high") {
        return note.quality_score >= 0.8
      }
      if (qualityFilter === "medium") {
        return note.quality_score >= 0.6
      }
      if (qualityFilter === "low") {
        return note.quality_score >= 0.4
      }
      return true
    })

    return filtered.sort((left, right) => {
      if (sortBy === "words") {
        return right.word_count - left.word_count
      }
      if (sortBy === "title") {
        return left.title.localeCompare(right.title)
      }
      return right.quality_score - left.quality_score
    })
  }, [notes, qualityFilter, search, sortBy])

  useEffect(() => {
    if (!filteredNotes.length) {
      setSelectedPath("")
      return
    }

    const selectedStillVisible = filteredNotes.some((note) => note.path === selectedPath)
    if (!selectedPath || !selectedStillVisible) {
      setSelectedPath(filteredNotes[0].path)
    }
  }, [filteredNotes, selectedPath])

  const totalFiles = vaultStats?.total_found ?? notes.length
  const selectedFiles = vaultStats?.passed_filter ?? notes.length
  const skippedFiles = Math.max(0, totalFiles - selectedFiles)
  const selectedNote = filteredNotes.find((note) => note.path === selectedPath) || filteredNotes[0] || null
  const selectionIndex = selectedNote
    ? filteredNotes.findIndex((note) => note.path === selectedNote.path) + 1
    : 0
  const noteDensity = selectedNote ? Math.max(12, Math.min(100, Math.round(selectedNote.word_count / 6))) : 12

  if (!jobId) {
    return <Navigate to="/" replace />
  }

  return (
    <Layout currentStep={3} contentClassName="max-w-7xl">
      <div className="space-y-4">
        <div className="flex flex-col gap-3 rounded-2xl border border-zinc-700/50 bg-zinc-900/70 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-zinc-100">
              {vaultStats?.passed_filter ?? notes.length} notes ready for generation
            </p>
            <p className="mt-1 text-sm text-zinc-500">
              Review any file, then generate one dataset for the whole vault.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => navigate("/configure")}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2.5 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
            >
              ← Back
            </button>
            <button
              type="button"
              onClick={() => navigate("/generate")}
              disabled={loading || notes.length === 0}
              className="rounded-lg bg-brand-600 px-4 py-2.5 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Generate Training Data →
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-700/50 bg-zinc-900/70 p-3">
          <div className="grid items-start gap-3 xl:grid-cols-[320px_minmax(0,1fr)]">
            <section className="rounded-xl border border-zinc-700/50 bg-zinc-950/60">
              <div className="grid grid-cols-3 gap-px rounded-t-xl border-b border-zinc-700/50 bg-zinc-800/80">
                {[
                  { label: "Total files", value: totalFiles },
                  { label: "Selected files", value: selectedFiles },
                  { label: "Skipped files", value: skippedFiles },
                ].map((item) => (
                  <div key={item.label} className="bg-zinc-950/70 px-4 py-3">
                    <p className="text-lg font-semibold text-zinc-100">{item.value}</p>
                    <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                      {item.label}
                    </p>
                  </div>
                ))}
              </div>

              <div className="border-b border-zinc-700/50 px-4 py-4">
                <p className="text-xs font-medium uppercase tracking-[0.24em] text-zinc-500">
                  Explorer
                </p>
                <div className="mt-3 space-y-3">
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search notes, tags, links..."
                    className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={qualityFilter}
                      onChange={(event) => setQualityFilter(event.target.value)}
                      className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
                    >
                      {qualityFilters.map((filter) => (
                        <option key={filter.value} value={filter.value}>
                          {filter.label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={sortBy}
                      onChange={(event) => setSortBy(event.target.value)}
                      className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
                    >
                      <option value="score">Top scored</option>
                      <option value="words">Longest</option>
                      <option value="title">A-Z</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="border-b border-zinc-700/50 px-4 py-3 text-xs text-zinc-500">
                Showing {filteredNotes.length} of {totalFiles} notes
              </div>

              <div className="max-h-[680px] overflow-y-auto p-2">
                {loading
                  ? Array.from({ length: 10 }).map((_, index) => (
                      <div
                        key={index}
                        className="mb-2 h-16 animate-pulse rounded-xl border border-zinc-700/40 bg-zinc-900/80"
                      />
                    ))
                  : filteredNotes.map((note) => {
                      const isActive = selectedNote?.path === note.path
                      return (
                        <button
                          key={note.path}
                          type="button"
                          onClick={() => setSelectedPath(note.path)}
                          className={[
                            "mb-2 w-full rounded-xl border px-3 py-3 text-left transition-all duration-150",
                            isActive
                              ? "border-brand-600 bg-brand-600/10 shadow-[inset_0_0_0_1px_rgba(16,185,129,0.2)]"
                              : "border-zinc-800 bg-zinc-900/80 hover:border-zinc-600 hover:bg-zinc-900",
                          ].join(" ")}
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-1 h-2.5 w-2.5 rounded-full bg-brand-400/80" />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-start justify-between gap-3">
                                <p className="truncate text-sm font-medium text-zinc-100">{note.title}</p>
                                <span className="font-mono text-xs text-zinc-500">
                                  {note.quality_score.toFixed(2)}
                                </span>
                              </div>
                              <p className="mt-1 truncate text-xs text-zinc-500">{formatDirectory(note.path)}</p>
                              <div className="mt-3 h-1.5 rounded-full bg-zinc-800">
                                <div
                                  className={`h-1.5 rounded-full transition-all duration-500 ${qualityTone(note.quality_score)}`}
                                  style={{ width: `${Math.max(8, note.quality_score * 100)}%` }}
                                />
                              </div>
                            </div>
                          </div>
                        </button>
                      )
                    })}

                {!loading && filteredNotes.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-zinc-700 px-4 py-10 text-center text-sm text-zinc-500">
                    No notes match the current filters.
                  </div>
                ) : null}
              </div>
            </section>

            <section className="rounded-xl border border-zinc-700/50 bg-zinc-950/60">
              <div className="flex items-center justify-between border-b border-zinc-700/50 px-5 py-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.24em] text-zinc-500">
                    Preview
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-zinc-100">
                    {selectedNote ? `${selectedNote.title}.md` : loading ? "Scanning vault..." : "No file selected"}
                  </h2>
                  {selectedNote ? (
                    <p className="mt-1 text-xs text-zinc-500">{formatPath(selectedNote.path)}</p>
                  ) : null}
                </div>
                {selectedNote ? (
                  <div className="rounded-full border border-zinc-700/50 bg-zinc-900 px-3 py-1 font-mono text-xs text-zinc-400">
                    {selectionIndex}/{filteredNotes.length}
                  </div>
                ) : null}
              </div>

              <div className="space-y-5 p-5">
                {error ? <p className="text-sm text-red-400">{error}</p> : null}

                {loading ? (
                  <div className="space-y-4">
                    <div className="h-5 w-48 animate-pulse rounded bg-zinc-800" />
                    <div className="h-40 animate-pulse rounded-xl bg-zinc-900" />
                    <div className="h-40 animate-pulse rounded-xl bg-zinc-900" />
                  </div>
                ) : selectedNote ? (
                  <>
                    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-700/50 bg-zinc-900 px-4 py-3 text-sm text-zinc-400">
                      <span>{selectedNote.word_count} words</span>
                      <span className="text-zinc-600">•</span>
                      <span>{qualityLabel(selectedNote.quality_score)}</span>
                      <span className="text-zinc-600">•</span>
                      <div className="flex items-center gap-2">
                        <span>Quality</span>
                        <div className="h-1.5 w-20 rounded-full bg-zinc-800">
                          <div
                            className={`h-1.5 rounded-full transition-all duration-500 ${qualityTone(selectedNote.quality_score)}`}
                            style={{ width: `${Math.max(8, selectedNote.quality_score * 100)}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-zinc-500">
                          {selectedNote.quality_score.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    <div className="grid gap-3 lg:grid-cols-3">
                      <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Folder</p>
                        <p className="mt-2 truncate text-sm text-zinc-200">{formatDirectory(selectedNote.path)}</p>
                      </div>
                      <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Tags</p>
                        <p className="mt-2 text-sm text-zinc-200">
                          {selectedNote.tags.length ? `${selectedNote.tags.length} attached` : "No tags"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Links</p>
                        <p className="mt-2 text-sm text-zinc-200">
                          {selectedNote.wikilinks.length
                            ? `${selectedNote.wikilinks.length} references`
                            : "No wikilinks"}
                        </p>
                      </div>
                    </div>

                    {(selectedNote.tags.length > 0 || selectedNote.wikilinks.length > 0) && (
                      <div className="grid gap-3 lg:grid-cols-2">
                        <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 px-4 py-4">
                          <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Tags</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {selectedNote.tags.length ? (
                              selectedNote.tags.slice(0, 8).map((tag) => (
                                <span
                                  key={tag}
                                  className="rounded-full border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300"
                                >
                                  #{tag}
                                </span>
                              ))
                            ) : (
                              <span className="text-sm text-zinc-500">No tags in this note.</span>
                            )}
                          </div>
                        </div>

                        <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 px-4 py-4">
                          <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Wikilinks</p>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {selectedNote.wikilinks.length ? (
                              selectedNote.wikilinks.slice(0, 8).map((link) => (
                                <span
                                  key={link}
                                  className="rounded-full border border-zinc-700 bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300"
                                >
                                  {link}
                                </span>
                              ))
                            ) : (
                              <span className="text-sm text-zinc-500">No wikilinks in this note.</span>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="rounded-2xl border border-zinc-700/50 bg-[#0b0d12]">
                      <div className="flex items-center gap-2 border-b border-zinc-700/50 px-4 py-3">
                        <span className="h-3 w-3 rounded-full bg-red-500/80" />
                        <span className="h-3 w-3 rounded-full bg-yellow-500/80" />
                        <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
                        <p className="ml-3 truncate font-mono text-xs text-zinc-500">
                          {selectedNote.title}.md
                        </p>
                      </div>
                      <div className="p-5">
                        <div
                          className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-5 font-mono text-sm leading-7 text-zinc-300"
                          style={{
                            backgroundImage:
                              "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)",
                            backgroundSize: `100% ${noteDensity}px`,
                          }}
                        >
                          {selectedNote.body_preview || "No preview available for this note."}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="rounded-xl border border-dashed border-zinc-700 px-4 py-12 text-center text-sm text-zinc-500">
                    Select a file from the explorer to preview it.
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      </div>
    </Layout>
  )
}
