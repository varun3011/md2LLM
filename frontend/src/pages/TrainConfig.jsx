import { useEffect, useState } from "react"
import { Navigate, useLocation, useNavigate } from "react-router-dom"

import { useMd2LLM } from "../App"
import Layout from "../components/Layout"

export default function TrainConfig() {
  const navigate = useNavigate()
  const location = useLocation()
  const { setCurrentStep } = useMd2LLM()

  const selectedModel = location.state?.selectedModel || ""
  const hfRepo = location.state?.hf_repo || selectedModel
  const goal = location.state?.goal || "knowledge"
  const jobId = location.state?.jobId || ""
  const pairsCount = location.state?.pairsCount || 0
  const hardware = location.state?.hardware || null

  const [outputName, setOutputName] = useState("")
  const [outputDir, setOutputDir] = useState("")
  const [epochs, setEpochs] = useState(3)
  const [learningRate, setLearningRate] = useState("auto")
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [config, setConfig] = useState(null)
  const [validating, setValidating] = useState(false)
  const [validated, setValidated] = useState(false)
  const [errors, setErrors] = useState([])
  const [sessionId, setSessionId] = useState("")
  const [recommendation, setRecommendation] = useState(null)

  useEffect(() => {
    setCurrentStep(4)
  }, [setCurrentStep])

  useEffect(() => {
    if (hardware) {
      void fetchRecommendation()
    }
  }, [hardware])

  useEffect(() => {
    if (!selectedModel) {
      return undefined
    }

    const timer = setTimeout(() => {
      void validateConfig()
    }, 600)

    return () => clearTimeout(timer)
  }, [selectedModel, hfRepo, goal, outputName, outputDir, epochs, learningRate, jobId, sessionId])

  async function fetchRecommendation() {
    try {
      const params = new URLSearchParams({
        ram_gb: String(hardware.ram_gb || 8),
        approach: hardware.training_approach || "mlx",
        vram_gb: String(hardware.vram_gb || 0),
        is_mac_silicon: String(hardware.is_mac_silicon || false),
      })
      const res = await fetch(`/api/training/training-recommendation?${params}`)
      const data = await res.json()
      setRecommendation(data)
    } catch (error) {
      console.error("Failed to get recommendation", error)
    }
  }

  async function validateConfig() {
    setValidating(true)
    setValidated(false)

    const form = new FormData()
    form.append("model_name", selectedModel)
    form.append("hf_repo", hfRepo)
    form.append("goal", goal)
    form.append("output_name", outputName)
    form.append("output_dir", outputDir)
    form.append("epochs", String(epochs))
    form.append("learning_rate", learningRate)
    form.append("job_id", jobId)
    if (sessionId) {
      form.append("session_id", sessionId)
    }

    try {
      const response = await fetch("/api/training/configure", {
        method: "POST",
        body: form,
      })
      const data = await response.json()
      setConfig(data)
      if (data.recommendation) {
        setRecommendation(data.recommendation)
      }
      setErrors(data.errors || [])
      setValidated(Boolean(data.valid))
      if (data.session_id) {
        setSessionId(data.session_id)
      }
    } catch {
      setErrors(["Failed to validate configuration"])
      setValidated(false)
    } finally {
      setValidating(false)
    }
  }

  function handleContinue() {
    navigate("/train/run", {
      state: {
        config,
        sessionId: sessionId || config?.session_id || "",
        selectedModel,
        hf_repo: hfRepo,
        goal,
        jobId,
        hardware,
        recommendation,
      },
    })
  }

  if (!selectedModel) {
    return <Navigate to="/select-model" replace />
  }

  const epochDescriptions = {
    1: "Quick pass - faster but less thorough",
    2: "Light training - good for large datasets (1000+ pairs)",
    3: "Standard - recommended for most vaults",
    4: "Deep training - good for small datasets",
    5: "Maximum - risk of overfitting on small datasets",
  }

  const lrDescriptions = {
    auto: "Let md2LLM pick based on your dataset size",
    "1e-4": "Conservative - safer for small datasets",
    "2e-4": "Standard - works well for most cases",
    "3e-4": "Aggressive - faster learning, higher risk",
  }

  return (
    <Layout currentStep={4}>
      <div className="grid gap-6 lg:grid-cols-5">
        <section className="space-y-6 lg:col-span-3">
          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
            <h1 className="text-2xl font-semibold text-zinc-100">Configure training</h1>
            <p className="mt-2 text-sm text-zinc-400">
              Review and adjust settings before fine-tuning starts.
            </p>
          </div>

          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
              Training model
            </p>
            <div className="mt-3 flex items-center justify-between gap-4">
              <div>
                <p className="font-mono text-sm font-medium text-zinc-100">{hfRepo}</p>
                <p className="mt-1 text-sm text-zinc-500">
                  {hardware?.os_display || "Your machine"} ·{" "}
                  {hardware?.approach_details?.name || "Auto-detected approach"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => navigate(-1)}
                className="text-xs text-zinc-500 transition-colors hover:text-zinc-300"
              >
                Change
              </button>
            </div>
          </div>

          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
              Output model name
            </label>
            <input
              type="text"
              value={outputName}
              onChange={(event) => setOutputName(event.target.value)}
              placeholder={`md2llm-${hfRepo.split("/").pop() || "model"}-0408`}
              className="mt-3 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
            />
            <p className="mt-2 text-xs text-zinc-600">
              Leave empty to auto-generate. Used as the Ollama model name.
            </p>
            {config?.output_name ? (
              <p className="mt-1 text-xs text-zinc-400">
                Will be saved as: <span className="font-mono text-brand-300">{config.output_name}</span>
              </p>
            ) : null}
          </div>

          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
              Output folder
            </label>
            <input
              type="text"
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              placeholder="models"
              className="mt-3 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2.5 text-sm text-zinc-100 focus:border-brand-600 focus:outline-none"
            />
            <p className="mt-2 text-xs text-zinc-600">
              Choose where the trained model should be written. The folder will be created if needed.
            </p>
            {config?.output_dir ? (
              <p className="mt-1 text-xs text-zinc-400">
                Folder: <span className="font-mono text-brand-300">{config.output_dir}</span>
              </p>
            ) : null}
          </div>

          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
              Training epochs
            </label>
            <div className="mt-3 flex items-center gap-4">
              <input
                type="range"
                min="1"
                max="5"
                value={epochs}
                onChange={(event) => setEpochs(parseInt(event.target.value, 10))}
                className="flex-1 accent-brand-600"
              />
              <span className="w-6 text-center text-lg font-medium text-zinc-100">{epochs}</span>
            </div>
            <div className="mt-3 flex justify-between">
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setEpochs(value)}
                  className={[
                    "rounded px-2 py-1 text-xs transition-colors",
                    epochs === value ? "bg-brand-600 text-white" : "text-zinc-500 hover:text-zinc-300",
                  ].join(" ")}
                >
                  {value}
                </button>
              ))}
            </div>
            <p className="mt-3 text-sm text-zinc-400">{epochDescriptions[epochs]}</p>

            {config?.pair_count && epochs >= 4 && config.pair_count > 500 ? (
              <div className="mt-3 rounded-lg border border-amber-700/30 bg-amber-900/20 p-3">
                <p className="text-xs text-amber-400">
                  {epochs} epochs on {config.pair_count} pairs may cause overfitting. Consider 2-3 epochs for larger datasets.
                </p>
              </div>
            ) : null}

            {config?.pair_count && epochs <= 2 && config.pair_count < 300 ? (
              <div className="mt-3 rounded-lg border border-amber-700/30 bg-amber-900/20 p-3">
                <p className="text-xs text-amber-400">
                  {epochs} epoch(s) may not be enough for {config.pair_count} pairs. Consider 3 epochs for better results.
                </p>
              </div>
            ) : null}
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((current) => !current)}
              className="flex items-center gap-1 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
            >
              <span>{showAdvanced ? "▼" : "▶"}</span>
              Advanced settings
            </button>

            {showAdvanced ? (
              <div className="mt-3 space-y-4 rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
                <div>
                  <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
                    Learning rate
                  </label>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {Object.entries(lrDescriptions).map(([value, description]) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => setLearningRate(value)}
                        className={[
                          "rounded-lg border p-3 text-left transition-colors",
                          learningRate === value
                            ? "border-brand-600 bg-brand-600/10"
                            : "border-zinc-700 hover:border-zinc-600",
                        ].join(" ")}
                      >
                        <p className="text-xs font-medium text-zinc-200">{value}</p>
                        <p className="mt-1 text-xs text-zinc-500">{description}</p>
                      </button>
                    ))}
                  </div>
                  {config?.learning_rate ? (
                    <p className="mt-2 text-xs text-zinc-500">
                      Using: {config.learning_rate} - {config.learning_rate_note}
                    </p>
                  ) : null}
                </div>

                {config ? (
                  <div>
                    <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
                      LoRA rank (auto)
                    </label>
                    <div className="mt-2 flex items-center justify-between rounded-lg bg-zinc-800 px-3 py-2">
                      <span className="text-sm text-zinc-400">rank = {config.lora_rank}</span>
                      <span className="text-xs text-zinc-600">
                        auto-calculated from {config.pair_count} pairs
                      </span>
                    </div>
                  </div>
                ) : null}

                {config ? (
                  <div>
                    <label className="block text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
                      Batch size (auto)
                    </label>
                    <div className="mt-2 flex items-center justify-between rounded-lg bg-zinc-800 px-3 py-2">
                      <span className="text-sm text-zinc-400">batch = {config.batch_size}</span>
                      <span className="text-xs text-zinc-600">auto-calculated from hardware</span>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {errors.length > 0 ? (
            <div className="rounded-xl border border-red-700/50 bg-red-900/20 p-4">
              <p className="text-sm font-medium text-red-400">Configuration errors</p>
              <ul className="mt-2 space-y-1">
                {errors.map((error) => (
                  <li key={error} className="text-xs text-red-300">
                    · {error}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>

        <aside className="space-y-4 lg:col-span-2">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-zinc-500">
            Training summary
          </p>

          <div className="space-y-3 rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
            {validating && !config ? (
              <div className="space-y-2 animate-pulse">
                {[1, 2, 3, 4, 5].map((item) => (
                  <div key={item} className="flex justify-between">
                    <div className="h-3 w-1/3 rounded bg-zinc-800" />
                    <div className="h-3 w-1/4 rounded bg-zinc-800" />
                  </div>
                ))}
              </div>
            ) : config ? (
              <>
                <SummaryRow label="Model" value={config.hf_repo || config.model_name} mono />
                <SummaryRow label="Output name" value={config.output_name} mono />
                <SummaryRow label="Output folder" value={config.output_dir} mono />
                <SummaryRow
                  label="Training pairs"
                  value={config.pair_count.toLocaleString()}
                  highlight={config.pair_count >= 300}
                />
                <SummaryRow label="Epochs" value={config.epochs} />
                <SummaryRow label="Learning rate" value={config.learning_rate} mono />
                <SummaryRow label="LoRA rank" value={config.lora_rank} />
                <SummaryRow label="Batch size" value={config.batch_size} />
                <SummaryRow label="Max seq length" value={config.max_seq_length} />
                <SummaryRow
                  label="Approach"
                  value={config.hardware?.approach_details?.name || config.hardware?.training_approach}
                />
              </>
            ) : (
              <p className="text-xs text-zinc-500">Validating configuration...</p>
            )}
          </div>

          {config?.time_estimate ? (
            <div
              className={[
                "rounded-xl border p-4",
                validated ? "border-emerald-700/30 bg-emerald-900/10" : "border-zinc-700/50 bg-zinc-900",
              ].join(" ")}
            >
              <p className="text-xs font-medium text-zinc-400">Estimated training time</p>
              <p className={["mt-2 text-2xl font-medium", validated ? "text-emerald-400" : "text-zinc-300"].join(" ")}>
                {config.time_estimate.display}
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                {config.time_estimate.breakdown.pairs} pairs · {config.time_estimate.breakdown.epochs} epochs ·{" "}
                {config.time_estimate.breakdown.approach}
              </p>
            </div>
          ) : null}

          {config?.output_path ? (
            <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
              <p className="text-xs text-zinc-500">Model will be saved to</p>
              <code className="mt-1 block break-all text-xs text-zinc-300">{config.output_path}.gguf</code>
            </div>
          ) : null}

          {config?.pair_count ? (
            <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
              <p className="text-xs font-medium text-zinc-400">Dataset quality</p>
              <div className="mt-3 space-y-2">
                <QualityIndicator
                  label="Pair count"
                  value={config.pair_count}
                  good={config.pair_count >= 300}
                  warning={config.pair_count >= 150 && config.pair_count < 300}
                  goodText="Good volume"
                  warningText="Minimum viable"
                  badText="Too few pairs"
                />
                <QualityIndicator
                  label="Epochs × pairs"
                  value={config.pair_count * config.epochs}
                  good={config.pair_count * config.epochs >= 600}
                  warning={config.pair_count * config.epochs >= 300}
                  goodText="Strong training signal"
                  warningText="Light training signal"
                  badText="Very light training"
                />
              </div>
            </div>
          ) : null}

          {pairsCount > 0 && !config?.pair_count ? (
            <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-4 text-xs text-zinc-500">
              Expected roughly {pairsCount} pairs from the previous step.
            </div>
          ) : null}
        </aside>
      </div>

      {recommendation && recommendation.show_colab ? (
        <div
          className={[
            "mt-6 rounded-xl border p-4",
            recommendation.colab_required
              ? "border-red-700/30 bg-red-900/10"
              : "border-amber-700/30 bg-amber-900/10",
          ].join(" ")}
        >
          <div className="flex items-start gap-3">
            <span
              className={[
                "flex-shrink-0 text-lg",
                recommendation.colab_required ? "text-red-400" : "text-amber-400",
              ].join(" ")}
            >
              ⚠
            </span>
            <div>
              <p
                className={[
                  "mb-1 text-sm font-medium",
                  recommendation.colab_required ? "text-red-400" : "text-amber-400",
                ].join(" ")}
              >
                {recommendation.colab_required ? "Local training not recommended" : "Local training may be unstable"}
              </p>
              <p className="text-xs text-zinc-400">{recommendation.message}</p>
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-8 flex items-center justify-between border-t border-zinc-800 pt-6">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="text-sm text-zinc-400 transition-colors hover:text-zinc-200"
        >
          ← Back
        </button>

        <div className="flex items-center gap-4">
          {validating ? <span className="text-sm text-zinc-500">Validating...</span> : null}
          {validated && !validating ? <span className="text-sm text-emerald-400">✓ Ready to train</span> : null}
          <button
            type="button"
            onClick={handleContinue}
            disabled={!validated || validating}
            className="rounded-lg bg-brand-600 px-6 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Start training →
          </button>
        </div>
      </div>
    </Layout>
  )
}

function SummaryRow({ label, value, mono = false, highlight = false }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-zinc-500">{label}</span>
      <span
        className={[
          "text-xs",
          highlight ? "font-medium text-emerald-400" : mono ? "font-mono text-zinc-300" : "text-zinc-200",
        ].join(" ")}
      >
        {value}
      </span>
    </div>
  )
}

function QualityIndicator({ label, good, warning, goodText, warningText, badText }) {
  const color = good ? "text-emerald-400" : warning ? "text-amber-400" : "text-red-400"
  const dot = good ? "●" : warning ? "◐" : "○"
  const text = good ? goodText : warning ? warningText : badText

  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className={["text-xs", color].join(" ")}>
        {dot} {text}
      </span>
    </div>
  )
}
