import { useEffect, useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"

import { useMd2LLM } from "../App"
import Layout from "../components/Layout"
import ProgressBar from "../components/ProgressBar"

function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const remaining = total % 60
  return `${minutes}m ${remaining}s`
}

export default function Generate() {
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [logs, setLogs] = useState([])
  const [startTime, setStartTime] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [completedElapsed, setCompletedElapsed] = useState(null)
  const [showInstructions, setShowInstructions] = useState(false)
  const [error, setError] = useState("")
  const { goal, outputDir, jobId, setJobId, setCurrentStep } = useMd2LLM()

  const isTerminal = job?.status === "complete" || job?.status === "error"
  const isComplete = job?.status === "complete"

  useEffect(() => {
    setCurrentStep(4)
  }, [setCurrentStep])

  useEffect(() => {
    if (!startTime || isTerminal) {
      return undefined
    }

    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => window.clearInterval(timer)
  }, [isTerminal, startTime])

  useEffect(() => {
    if (!startTime || !isTerminal || completedElapsed !== null) {
      return
    }

    const finalElapsed = Math.floor((Date.now() - startTime) / 1000)
    setElapsed(finalElapsed)
    setCompletedElapsed(finalElapsed)
  }, [completedElapsed, isTerminal, startTime])

  useEffect(() => {
    let active = true

    async function startGeneration() {
      if (!jobId) {
        return
      }

      if (job?.status && job.status !== "ready" && job.status !== "error") {
        return
      }

      try {
        const formData = new FormData()
        formData.append("job_id", jobId)
        formData.append("goal", goal)
        formData.append("min_quality", "0.4")
        formData.append("output_dir", outputDir)

        const response = await fetch("/api/generate", {
          method: "POST",
          body: formData,
        })

        if (!response.ok) {
          const data = await response.json().catch(() => ({}))
          throw new Error(data.detail || "Failed to start generation")
        }

        const data = await response.json()
        if (active) {
          setJobId(data.job_id)
          setCompletedElapsed(null)
          setElapsed(0)
          setStartTime(Date.now())
        }
      } catch (generationError) {
        if (active) {
          setError(generationError.message)
        }
      }
    }

    void startGeneration()
    return () => {
      active = false
    }
  }, [goal, job, jobId, outputDir, setJobId])

  useEffect(() => {
    if (!jobId) {
      return undefined
    }

    const source = new EventSource(`/api/progress/${jobId}`)

    source.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setJob(data)
      setLogs((current) => {
        const next = [
          {
            id: `${data.status}-${data.progress}-${data.pairs}-${data.message}`,
            text: `${data.status === "complete" ? "✓" : "→"} ${data.message}`,
          },
          ...current,
        ]
        return next.slice(0, 5)
      })

      if (data.status === "complete" || data.status === "error") {
        source.close()
      }
    }

    source.onerror = () => {
      setError("Lost connection to the progress stream.")
      source.close()
    }

    return () => {
      source.close()
    }
  }, [jobId])

  if (!jobId) {
    return <Navigate to="/" replace />
  }

  const estimatedRemaining = (() => {
    const duration = completedElapsed ?? elapsed
    if (!job || !job.total || !job.progress || duration <= 0) {
      return null
    }
    const rate = job.progress / duration
    if (rate <= 0) {
      return null
    }
    return Math.max(0, Math.round((job.total - job.progress) / rate))
  })()
  const displayElapsed = completedElapsed ?? elapsed

  return (
    <Layout currentStep={4}>
      <div className="space-y-6">
        <section className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
          <h1 className="text-2xl font-semibold text-zinc-100">
            {isComplete ? "Training data ready" : "Generating training data..."}
          </h1>

          {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}

          <div className="mt-6 rounded-2xl border border-zinc-700/50 bg-zinc-950/60 p-6">
            {isComplete ? (
              <div className="space-y-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-lg text-zinc-100">Your dataset is ready</p>
                    <p className="mt-1 text-sm text-zinc-500">
                      Review the hardware recommendation and choose the base model in the next step.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      navigate("/select-model", {
                        state: {
                          goal,
                          jobId,
                          pairsCount: job?.pairs ?? 0,
                        },
                      })
                    }
                    className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800"
                  >
                    Continue to model selection →
                  </button>
                </div>
                <div className="rounded-xl border border-zinc-700/50 bg-zinc-900/70 p-4">
                  <p className="text-sm font-medium text-zinc-200">✓ Training data generated</p>
                  <p className="mt-2 text-sm text-zinc-400">
                    {job?.pairs ?? 0} training pairs generated from {job?.total ?? 0} notes in{" "}
                    {formatDuration(displayElapsed)}.
                  </p>
                  <p className="mt-2 text-xs text-zinc-500">
                    Saved to {job?.output_path ?? outputDir}
                  </p>
                </div>
                <a
                  href={`/api/download/${jobId}`}
                  className="inline-flex rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
                >
                  Download training_data.jsonl
                </a>
              </div>
            ) : (
              <div className="space-y-6">
                <ProgressBar value={job?.progress ?? 0} total={job?.total ?? 0} />
                <p className="text-sm text-zinc-300">{job?.pairs ?? 0} pairs generated so far</p>
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-zinc-600">
                    Currently processing
                  </p>
                  <p className="mt-2 text-sm text-zinc-200">{job?.message ?? "Waiting for progress..."}</p>
                </div>
                <p className="text-sm text-zinc-500">
                  Elapsed: {formatDuration(displayElapsed)}
                  {estimatedRemaining !== null
                    ? ` · Est. remaining: ${formatDuration(estimatedRemaining)}`
                    : ""}
                </p>
              </div>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
          <p className="mb-4 text-sm font-medium text-zinc-200">Live log</p>
          <div className="space-y-2 rounded-2xl border border-zinc-700/50 bg-zinc-950/60 p-4 font-mono text-xs text-zinc-400">
            {logs.length > 0 ? logs.map((line) => <p key={line.id}>{line.text}</p>) : <p>Waiting for updates...</p>}
          </div>
        </section>

        {isComplete ? (
          <section className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
            <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-zinc-100">Next: model recommendation</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
                  md2LLM will detect your Ollama models and hardware, then recommend the best
                  base model before training starts.
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={() => setShowInstructions(true)}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
                >
                  View notes
                </button>
                <button
                  type="button"
                  onClick={() =>
                    navigate("/select-model", {
                      state: {
                        goal,
                        jobId,
                        pairsCount: job?.pairs ?? 0,
                      },
                    })
                  }
                  className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800"
                >
                  Continue to model selection →
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {showInstructions ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
            <div className="w-full max-w-lg rounded-2xl border border-zinc-700/50 bg-zinc-900 p-6">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-100">What happens next</h2>
                <button
                  type="button"
                  onClick={() => setShowInstructions(false)}
                  className="text-zinc-500 transition-colors hover:text-zinc-200"
                >
                  Close
                </button>
              </div>
              <div className="mt-5 space-y-4 text-sm text-zinc-300">
                <p>Step 1 recommends the best installed Ollama model for your goal.</p>
                <p>Step 2 detects hardware and suggests MLX, Unsloth, CPU, or Colab.</p>
                <p>Training execution itself is not part of this step yet.</p>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </Layout>
  )
}
