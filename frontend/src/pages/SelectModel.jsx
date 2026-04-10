import { useState, useEffect } from "react"
import { useNavigate, useLocation } from "react-router-dom"

import Layout from "../components/Layout"

export default function SelectModel() {
  const navigate = useNavigate()
  const location = useLocation()

  const goal = location.state?.goal || "knowledge"
  const jobId = location.state?.jobId || ""
  const pairsCount = location.state?.pairsCount || 0

  const [recommendations, setRecommendations] = useState([])
  const [loading, setLoading] = useState(true)
  const [hardware, setHardware] = useState(location.state?.hardware || null)
  const [selectedRepo, setSelectedRepo] = useState("")
  const [customRepo, setCustomRepo] = useState("")
  const [customError, setCustomError] = useState("")
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    fetchRecommendations()
  }, [])

  async function fetchRecommendations() {
    setLoading(true)
    try {
      let activeHardware = hardware
      if (!activeHardware?.training_approach) {
        const hardwareRes = await fetch("/api/training/hardware")
        if (hardwareRes.ok) {
          activeHardware = await hardwareRes.json()
          setHardware(activeHardware)
        }
      }

      const approach = activeHardware?.training_approach || "mlx"
      const ramGb = activeHardware?.ram_gb || 16

      const res = await fetch(
        `/api/training/recommended-models?approach=${approach}&goal=${goal}&ram_gb=${ramGb}`
      )
      const data = await res.json()
      setRecommendations(data.models || [])

      if (data.models?.length > 0) {
        setSelectedRepo(data.models[0].hf_repo)
      }
    } catch (e) {
      console.error("Failed to fetch recommendations", e)
    }
    setLoading(false)
  }

  async function handleCustomRepo() {
    if (!customRepo.trim()) return
    setChecking(true)
    setCustomError("")

    const repo = customRepo.trim()

    if (!repo.includes("/")) {
      setCustomError(
        "Must be a valid HuggingFace repo ID like: Qwen/Qwen2.5-1.5B-Instruct"
      )
      setChecking(false)
      return
    }

    try {
      const res = await fetch(
        `/api/training/check-model?hf_repo=${encodeURIComponent(repo)}`
      )
      const data = await res.json()

      if (data.supported) {
        setSelectedRepo(repo)
        setCustomError("")
      } else {
        setCustomError(data.message || "Model not found on HuggingFace")
      }
    } catch (e) {
      setCustomError("Failed to check model - is the server running?")
    }

    setChecking(false)
  }

  function handleContinue() {
    navigate("/train/config", {
      state: {
        selectedModel: selectedRepo,
        hf_repo: selectedRepo,
        goal,
        jobId,
        pairsCount,
        hardware,
      },
    })
  }

  return (
    <Layout currentStep={4}>
      <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-8">
        <h1 className="mb-1 text-2xl font-medium text-zinc-100">
          Choose training model
        </h1>
        <p className="text-sm text-zinc-400">
          Select a model from HuggingFace to fine-tune on your notes.
          The model will be downloaded once and cached locally.
        </p>
      </div>

      {hardware?.os_display && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
          <span className="text-sm text-zinc-400">
            Detected hardware:
          </span>
          <span className="text-sm font-medium text-zinc-200">
            {hardware.os_display}
          </span>
          {hardware.ram_gb && (
            <>
              <span className="text-zinc-600">·</span>
              <span className="text-sm text-zinc-400">
                {hardware.ram_gb} GB RAM
              </span>
            </>
          )}
          {hardware.approach_details?.name && (
            <>
              <span className="text-zinc-600">·</span>
              <span className="text-sm text-brand-400">
                {hardware.approach_details.name}
              </span>
            </>
          )}
        </div>
      )}

      <div className="mb-6">
        <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
          Recommended for your hardware
        </p>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-24 animate-pulse rounded-xl border border-zinc-700/50 bg-zinc-900"
              />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {recommendations.map((model) => (
              <button
                key={model.hf_repo}
                onClick={() => setSelectedRepo(model.hf_repo)}
                className={`w-full rounded-xl border p-4 text-left transition-all ${
                  selectedRepo === model.hf_repo
                    ? "border-brand-600 bg-brand-600/10"
                    : "border-zinc-700/50 bg-zinc-900 hover:border-zinc-600"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="font-medium text-zinc-100">
                        {model.display_name}
                      </span>
                      {model.top_pick && (
                        <span className="rounded-full bg-brand-600/20 px-2 py-0.5 text-xs text-brand-400">
                          Top pick
                        </span>
                      )}
                      <span className={`rounded-full px-2 py-0.5 text-xs ${
                        model.badge_color === "green"
                          ? "bg-green-900/30 text-green-400"
                          : "bg-amber-900/30 text-amber-400"
                      }`}>
                        {model.badge}
                      </span>
                    </div>

                    <p className="mb-1 font-mono text-xs text-zinc-500">
                      {model.hf_repo}
                    </p>

                    <p className="text-sm text-zinc-400">
                      {model.description}
                    </p>

                    <div className="mt-2 flex gap-3">
                      <span className="text-xs text-zinc-500">
                        {model.size_gb} GB download
                      </span>
                      <span className="text-xs text-zinc-600">·</span>
                      <span className="text-xs text-zinc-500">
                        {model.min_ram_gb}+ GB RAM needed
                      </span>
                    </div>
                  </div>

                  <div className={`ml-3 mt-1 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border-2 ${
                    selectedRepo === model.hf_repo
                      ? "border-brand-600 bg-brand-600"
                      : "border-zinc-600"
                  }`}>
                    {selectedRepo === model.hf_repo && (
                      <div className="h-2 w-2 rounded-full bg-white" />
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="mb-6 rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
        <p className="mb-1 text-sm font-medium text-zinc-300">
          Or use any HuggingFace model
        </p>
        <p className="mb-3 text-xs text-zinc-500">
          Enter any HuggingFace repo ID - must support text generation
          and be in safetensors format
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={customRepo}
            onChange={(e) => setCustomRepo(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCustomRepo()}
            placeholder="e.g. Qwen/Qwen3-1.7B"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
          />
          <button
            onClick={handleCustomRepo}
            disabled={checking || !customRepo.trim()}
            className="rounded-lg bg-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-600 disabled:opacity-50"
          >
            {checking ? "Checking..." : "Use this"}
          </button>
        </div>

        {customError && (
          <p className="mt-2 text-xs text-red-400">{customError}</p>
        )}

        {selectedRepo && !recommendations.find((model) => model.hf_repo === selectedRepo) && (
          <div className="mt-3 rounded-lg border border-brand-600/30 bg-brand-600/10 p-3">
            <p className="text-xs font-medium text-brand-400">
              ✓ Custom model selected
            </p>
            <p className="mt-0.5 font-mono text-xs text-zinc-400">
              {selectedRepo}
            </p>
          </div>
        )}

        <div className="mt-3">
          <p className="mb-1 text-xs text-zinc-600">Examples:</p>
          <div className="flex flex-wrap gap-2">
            {[
              "Qwen/Qwen3-1.7B",
              "Qwen/Qwen3-4B",
              "google/gemma-2-2b-it",
            ].map((example) => (
              <button
                key={example}
                onClick={() => setCustomRepo(example)}
                className="font-mono text-xs text-zinc-500 transition-colors hover:text-zinc-300"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mb-8 rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
        <p className="mb-2 text-xs font-medium text-zinc-400">
          What happens next
        </p>
        <div className="space-y-1">
          {[
            "Model downloads from HuggingFace (once, then cached)",
            "MLX fine-tunes it on your training data",
            "Result saved as .gguf file in models/ folder",
            "Load into Ollama and chat with your model",
          ].map((step, i) => (
            <div key={step} className="flex items-start gap-2">
              <span className="mt-0.5 text-xs text-brand-400">
                {i + 1}.
              </span>
              <span className="text-xs text-zinc-400">{step}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-zinc-800 pt-6">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-zinc-400 transition-colors hover:text-zinc-200"
        >
          ← Back
        </button>

        <div className="flex items-center gap-4">
          {selectedRepo && (
            <span className="text-sm text-zinc-400">
              Selected:{" "}
              <span className="font-mono text-xs text-zinc-200">
                {selectedRepo}
              </span>
            </span>
          )}
          <button
            onClick={handleContinue}
            disabled={!selectedRepo}
            className="rounded-lg bg-brand-600 px-6 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continue →
          </button>
        </div>
      </div>
      </div>
    </Layout>
  )
}
