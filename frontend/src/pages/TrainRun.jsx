import { useEffect, useRef, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"

import { useMd2LLM } from "../App"
import DepsCheck from "../components/DepsCheck"
import Layout from "../components/Layout"

export default function TrainRun() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setCurrentStep } = useMd2LLM()
  const config = location.state?.config
  const selectedModel = location.state?.selectedModel || ""
  const hfRepo = location.state?.hf_repo || location.state?.selectedModel || ""
  const goal = location.state?.goal || "knowledge"
  const jobId = location.state?.jobId || ""
  const sessionId = location.state?.sessionId || config?.session_id || ""
  const approach = location.state?.hardware?.training_approach || config?.hardware?.training_approach || "mlx"
  const recommendation = location.state?.recommendation || config?.recommendation || null
  const colabRequired = recommendation?.colab_required === true
  const colabRecommended = recommendation?.colab_recommended === true

  const [phase, setPhase] = useState("check")
  const [modelCheck, setModelCheck] = useState(null)
  const [checkLoading, setCheckLoading] = useState(true)
  const [depsReady, setDepsReady] = useState(false)
  const [trainingJobId, setTrainingJobId] = useState(null)
  const [trainingState, setTrainingState] = useState(null)
  const [logLines, setLogLines] = useState([])
  const logRef = useRef(null)
  const eventSourceRef = useRef(null)

  useEffect(() => {
    setCurrentStep(4)
  }, [setCurrentStep])

  useEffect(() => {
    setDepsReady(false)
  }, [approach])

  useEffect(() => {
    if (
      (phase === "ready" || phase === "download_required" || phase === "colab_required") &&
      (colabRequired || approach === "cpu" || approach === "colab")
    ) {
      setPhase("colab_steps")
    }
  }, [approach, colabRequired, phase])

  useEffect(() => {
    void checkModel()
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logLines])

  async function checkModel() {
    setCheckLoading(true)
    try {
      const res = await fetch(`/api/training/check-model?hf_repo=${encodeURIComponent(hfRepo)}`)
      const data = await res.json()
      setModelCheck(data)
      setPhase(data.needs_token_setup ? "token_required" : data.cached ? "ready" : "download_required")
    } catch {
      setPhase("error")
    }
    setCheckLoading(false)
  }

  async function startTraining() {
    setPhase("training")
    addLog("Starting training...")

    try {
      const form = new FormData()
      form.append("session_id", sessionId)

      const res = await fetch("/api/training/start", {
        method: "POST",
        body: form,
      })
      const data = await res.json()

      if (!res.ok) {
        const detail = data.detail
        if (detail?.error === "colab_required") {
          setTrainingState({
            status: "error",
            error: detail.message,
            recommendation: detail.recommendation,
          })
          setPhase("colab_steps")
          return
        }
        throw new Error(typeof detail === "string" ? detail : detail?.message || "Failed to start training")
      }

      setTrainingJobId(data.job_id)
      connectToProgress(data.job_id)
    } catch (error) {
      setPhase("error")
      addLog(`Error: ${error.message}`)
    }
  }

  function connectToProgress(jid) {
    const es = new EventSource(`/api/training/progress/${jid}`)
    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data)
        setTrainingState(state)
        addLog(state.message)

        if (state.status === "complete") {
          setPhase("complete")
          es.close()
        } else if (state.status === "error") {
          if (state.error === "colab_required") {
            setPhase("colab_steps")
          } else {
            setPhase("error")
          }
          es.close()
        }
      } catch (error) {
        console.error("SSE parse error", error)
      }
    }

    es.onerror = () => {
      es.close()
      if (phase !== "complete") {
        addLog("Connection lost - check server logs")
      }
    }
  }

  function addLog(message) {
    if (!message) return
    setLogLines((prev) => {
      const ts = new Date().toLocaleTimeString()
      return [...prev.slice(-50), `[${ts}] ${message}`]
    })
  }

  return (
    <Layout currentStep={4}>
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-8">
          <h1 className="mb-1 text-2xl font-medium text-zinc-100">Training</h1>
          <p className="text-sm text-zinc-400">
            Fine-tuning <span className="font-mono text-zinc-300">{hfRepo}</span> on your notes
          </p>
          <p className="mt-1 text-xs text-zinc-600">
            Goal: {goal} {jobId ? `· Job ${jobId}` : ""} {trainingJobId ? `· Training ${trainingJobId}` : ""}
          </p>
        </div>

        {(phase === "check" || checkLoading) && (
          <StatusCard
            icon="○"
            iconColor="text-zinc-400"
            title="Checking model cache"
            subtitle="Looking for cached model files..."
            loading
          />
        )}

        {phase === "token_required" && modelCheck && (
          <div className="space-y-4 rounded-xl border border-amber-700/50 bg-amber-900/20 p-6">
            <div>
              <p className="mb-1 font-medium text-amber-400">HuggingFace token required</p>
              <p className="text-sm text-zinc-400">{modelCheck.hf_repo} requires accepting the model license</p>
            </div>
            <ol className="space-y-2">
              {modelCheck.setup_instructions?.steps.map((step, index) => (
                <li key={step} className="flex gap-2 text-sm text-zinc-300">
                  <span className="flex-shrink-0 font-medium text-amber-400">{index + 1}.</span>
                  {step}
                </li>
              ))}
            </ol>
            <div className="flex gap-3 pt-2">
              <button
                onClick={checkModel}
                className="rounded-lg bg-amber-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600"
              >
                I have set my token → Check again
              </button>
              <button
                onClick={() => navigate(-1)}
                className="text-sm text-zinc-400 transition-colors hover:text-zinc-200"
              >
                ← Choose different model
              </button>
            </div>
          </div>
        )}

        {phase === "ready" && modelCheck && (
          <div className="space-y-4">
            <StatusCard
              icon="✓"
              iconColor="text-green-400"
              title="Model ready"
              subtitle={`${modelCheck.hf_repo} found in local cache`}
            />

            {!colabRequired && (
              <div>
                <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Training dependencies
                </p>
                <DepsCheck approach={approach} onReady={() => setDepsReady(true)} />
              </div>
            )}

            {!colabRequired && !colabRecommended && depsReady && (
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-zinc-200">Ready to start training</p>
                    <p className="mt-0.5 text-sm text-zinc-500">
                      {config?.pair_count || 0} pairs · {config?.epochs || 3} epochs ·{" "}
                      {config?.time_estimate?.display || "~20 min"}
                    </p>
                  </div>
                  <button
                    onClick={startTraining}
                    className="rounded-lg bg-brand-600 px-6 py-2 font-medium text-white transition-colors hover:bg-brand-800"
                  >
                    Start →
                  </button>
                </div>
              </div>
            )}

            {!colabRequired && colabRecommended && (
              <div className="space-y-3">
                <div className="rounded-xl border border-amber-700/30 bg-amber-900/10 p-4">
                  <p className="mb-1 text-sm font-medium text-amber-400">⚠ Low RAM warning</p>
                  <p className="text-sm text-zinc-400">{recommendation?.message}</p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-brand-600/50 bg-zinc-900 p-4">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded-full bg-brand-600/20 px-2 py-0.5 text-xs font-medium text-brand-400">
                        Recommended
                      </span>
                    </div>
                    <p className="mb-1 text-sm font-medium text-zinc-200">Google Colab</p>
                    <p className="mb-3 text-xs text-zinc-500">Free GPU · 15-20 min · No freezing</p>
                    <button
                      onClick={() => setPhase("colab_steps")}
                      className="w-full rounded-lg bg-brand-600 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-800"
                    >
                      Use Colab →
                    </button>
                  </div>

                  <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded-full bg-amber-900/20 px-2 py-0.5 text-xs font-medium text-amber-400">
                        May freeze
                      </span>
                    </div>
                    <p className="mb-1 text-sm font-medium text-zinc-200">Train locally</p>
                    <p className="mb-3 text-xs text-zinc-500">Uses all your RAM · Risky on 8GB</p>
                    <button
                      onClick={startTraining}
                      disabled={!depsReady}
                      className="w-full rounded-lg bg-zinc-700 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {depsReady ? "Train anyway" : "Waiting for dependencies"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {colabRequired && <ColabSteps jobId={jobId} />}
          </div>
        )}

        {phase === "colab_steps" && <ColabSteps jobId={jobId} />}

        {phase === "download_required" && modelCheck && !colabRequired && (
          <div className="space-y-4">
            <div className="space-y-4 rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
              <div>
                <p className="mb-1 font-medium text-zinc-100">First time setup</p>
                <p className="text-sm text-zinc-400">The training version of this model needs to be downloaded once</p>
              </div>
              <div className="space-y-2 rounded-lg bg-zinc-800 p-4">
                <div className="flex justify-between">
                  <span className="text-sm text-zinc-400">Model</span>
                  <span className="text-sm font-mono text-zinc-200">{modelCheck.hf_repo}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-zinc-400">Download size</span>
                  <span className="text-sm text-zinc-200">~{modelCheck.size_gb} GB</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-zinc-400">Cached after</span>
                  <span className="text-sm text-green-400">✓ Never downloaded again</span>
                </div>
              </div>
            </div>

            <div>
              <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
                Training dependencies
              </p>
              <DepsCheck approach={approach} onReady={() => setDepsReady(true)} />
            </div>

            {depsReady && (
              <button
                onClick={startTraining}
                className="w-full rounded-lg bg-brand-600 py-3 font-medium text-white transition-colors hover:bg-brand-800"
              >
                Download and start training →
              </button>
            )}
          </div>
        )}

        {phase === "training" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
              <div className="mb-3 flex items-center justify-between">
                <p className="font-medium text-zinc-200">{trainingState?.message || "Starting..."}</p>
                <span className="text-sm text-zinc-400">{trainingState?.progress || 0}%</span>
              </div>

              <div className="mb-3 h-2 w-full rounded-full bg-zinc-800">
                <div
                  className="h-2 rounded-full bg-brand-600 transition-all duration-500"
                  style={{ width: `${trainingState?.progress || 0}%` }}
                />
              </div>

              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-xs text-zinc-500">Step</p>
                  <p className="text-sm font-medium text-zinc-200">
                    {trainingState?.current_step || 0} / {trainingState?.total_steps || "?"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-zinc-500">Loss</p>
                  <p className="text-sm font-medium text-zinc-200">{trainingState?.loss ?? "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-zinc-500">Phase</p>
                  <p className="text-sm font-medium capitalize text-zinc-200">
                    {trainingState?.phase?.replace("_", " ") || "starting"}
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
              <p className="mb-2 text-xs font-medium text-zinc-500">Training log</p>
              <div ref={logRef} className="h-48 space-y-1 overflow-y-auto font-mono">
                {logLines.map((line, index) => (
                  <p key={`${line}-${index}`} className="text-xs text-zinc-400">
                    {line}
                  </p>
                ))}
                {logLines.length === 0 && <p className="text-xs text-zinc-600">Waiting for output...</p>}
              </div>
            </div>

            <p className="text-center text-xs text-zinc-600">Do not close this window while training is running</p>
          </div>
        )}

        {phase === "complete" && trainingState && (
          <div className="space-y-4">
            <div className="rounded-xl border border-green-700/50 bg-green-900/20 p-6 text-center">
              <p className="mb-3 text-4xl text-green-400">✓</p>
              <p className="mb-1 text-lg font-medium text-zinc-100">Training complete</p>
              <p className="text-sm text-zinc-400">Your model is ready</p>
            </div>

            <div className="space-y-2 rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
              <p className="mb-2 text-xs font-medium text-zinc-400">Load into Ollama to start chatting:</p>
              <code className="block rounded bg-zinc-800 px-3 py-2 text-xs text-green-400">
                ollama create {config?.output_name || "my-model"} -f training/Modelfile
              </code>
              <code className="block rounded bg-zinc-800 px-3 py-2 text-xs text-green-400">
                ollama run {config?.output_name || "my-model"}
              </code>
            </div>

            <button
              onClick={() => navigate("/chat", { state: { model: config?.output_name } })}
              className="w-full rounded-lg bg-brand-600 py-3 font-medium text-white transition-colors hover:bg-brand-800"
            >
              Open chat with your model →
            </button>
          </div>
        )}

        {phase === "colab_required" && <ColabSteps jobId={jobId} />}

        {phase === "error" && trainingState?.error_oom && (
          <div className="space-y-4">
            <div className="rounded-xl border border-red-700/30 bg-red-900/20 p-4">
              <p className="mb-1 text-sm font-medium text-red-400">Training failed - not enough RAM</p>
              <p className="text-sm text-zinc-400">
                Your Mac ran out of memory during training. Use Google Colab instead.
              </p>
            </div>
            <ColabSteps jobId={jobId} />
          </div>
        )}

        {phase === "error" && !trainingState?.error_oom && (
          <div className="space-y-4 rounded-xl border border-red-700/50 bg-red-900/20 p-6">
            <p className="font-medium text-red-400">Training failed</p>
            <p className="text-sm text-zinc-400">{trainingState?.error || "An unexpected error occurred"}</p>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setPhase("ready")
                  setTrainingState(null)
                  setLogLines([])
                }}
                className="rounded-lg bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600"
              >
                Try again
              </button>
              <button
                onClick={() => navigate(-1)}
                className="text-sm text-zinc-400 transition-colors hover:text-zinc-200"
              >
                ← Back to config
              </button>
            </div>
          </div>
        )}
      </div>
    </Layout>
  )
}

function StatusCard({ icon, iconColor, title, subtitle, loading = false }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
      <span className={`text-2xl ${iconColor} ${loading ? "animate-pulse" : ""}`}>{icon}</span>
      <div>
        <p className="font-medium text-zinc-200">{title}</p>
        <p className="text-sm text-zinc-500">{subtitle}</p>
      </div>
    </div>
  )
}

function ColabSteps({ jobId }) {
  const navigate = useNavigate()
  const colabUrl =
    "https://colab.research.google.com/github/yourusername/md2LLM/blob/main/training/md2LLM_colab.ipynb"

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-blue-700/50 bg-blue-900/20 p-5">
        <p className="mb-1 font-medium text-blue-400">Train on Google Colab - free</p>
        <p className="text-sm text-zinc-400">Free GPU provided by Google. Takes 15-20 minutes. No account upgrade needed.</p>
      </div>

      <div className="divide-y divide-zinc-800 rounded-xl border border-zinc-700/50 bg-zinc-900">
        <div className="flex gap-4 p-4">
          <StepNumber n={1} />
          <div className="flex-1">
            <p className="mb-2 text-sm font-medium text-zinc-200">Download your training data</p>
            <button
              onClick={() => {
                if (jobId) {
                  window.open(`/api/download/${jobId}`)
                }
              }}
              disabled={!jobId}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Download training_data.jsonl
            </button>
          </div>
        </div>

        <div className="flex gap-4 p-4">
          <StepNumber n={2} />
          <div className="flex-1">
            <p className="mb-2 text-sm font-medium text-zinc-200">Open the md2LLM Colab notebook</p>
            <a
              href={colabUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-600"
            >
              Open in Google Colab →
            </a>
            <p className="mt-1 text-xs text-zinc-600">Free Google account required</p>
          </div>
        </div>

        <div className="flex gap-4 p-4">
          <StepNumber n={3} />
          <div className="flex-1">
            <p className="mb-2 text-sm font-medium text-zinc-200">In Colab</p>
            <ul className="space-y-1">
              {[
                "Upload training_data.jsonl when Cell 2 runs",
                "Edit Cell 3 to change model if you want",
                "Click Runtime → Run all",
                "Wait 15-20 minutes",
                "Model downloads automatically when done",
              ].map((step) => (
                <li key={step} className="flex gap-2 text-xs text-zinc-400">
                  <span className="flex-shrink-0 text-zinc-600">·</span>
                  {step}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="flex gap-4 p-4">
          <StepNumber n={4} />
          <div className="flex-1">
            <p className="mb-2 text-sm font-medium text-zinc-200">Move model to md2LLM</p>
            <p className="mb-2 text-xs text-zinc-400">Move the downloaded .gguf file to your models/ folder:</p>
            <code className="block rounded-lg bg-zinc-800 px-3 py-2 font-mono text-xs text-green-400">
              mv ~/Downloads/*.gguf ~/Desktop/md2LLM/models/
            </code>
          </div>
        </div>

        <div className="flex gap-4 p-4">
          <StepNumber n={5} done />
          <div className="flex-1">
            <p className="mb-2 text-sm font-medium text-zinc-200">Load into Ollama and chat</p>
            <p className="mb-2 text-xs text-zinc-400">Run this command then come back to chat:</p>
            <code className="mb-3 block rounded-lg bg-zinc-800 px-3 py-2 font-mono text-xs text-green-400">
              ollama create my-model -f training/Modelfile
            </code>
            <button
              onClick={() => navigate("/chat")}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-800"
            >
              I have my model → Open chat
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function StepNumber({ n, done = false }) {
  return (
    <div
      className={[
        "mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-medium",
        done ? "bg-green-700/30 text-green-400" : "bg-brand-600/20 text-brand-400",
      ].join(" ")}
    >
      {done ? "✓" : n}
    </div>
  )
}
