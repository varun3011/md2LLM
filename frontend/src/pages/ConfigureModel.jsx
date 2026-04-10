import { useEffect, useState } from "react"
import { Navigate, useNavigate } from "react-router-dom"

import { useMd2LLM } from "../App"
import Layout from "../components/Layout"

const goals = [
  {
    id: "knowledge",
    title: "Knowledge",
    description: "Query everything you have studied",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="12" cy="12" r="4.5" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.2 2.2M16.9 16.9l2.2 2.2M19.1 4.9l-2.2 2.2M7.1 16.9l-2.2 2.2" />
      </svg>
    ),
  },
  {
    id: "style",
    title: "Style",
    description: "Write in your voice and tone",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M12 20h9" />
        <path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4Z" />
      </svg>
    ),
  },
  {
    id: "reasoning",
    title: "Reasoning",
    description: "Connect ideas the way you do",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="6" cy="6" r="2.5" />
        <circle cx="18" cy="6" r="2.5" />
        <circle cx="12" cy="18" r="2.5" />
        <path d="M8.3 7.3 10.7 16M15.7 7.3 13.3 16M8.5 6h7" />
      </svg>
    ),
  },
  {
    id: "chatbot",
    title: "Chatbot",
    description: "Conversational version of you",
    icon: (
      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M6 17.5 3 21V5.8A1.8 1.8 0 0 1 4.8 4h14.4A1.8 1.8 0 0 1 21 5.8v9.4a1.8 1.8 0 0 1-1.8 1.8H6Z" />
      </svg>
    ),
  },
]

export default function ConfigureModel() {
  const navigate = useNavigate()
  const [connectionMessage, setConnectionMessage] = useState("")
  const [error, setError] = useState("")
  const [serverOpenAIKeySet, setServerOpenAIKeySet] = useState(false)
  const [ollamaModels, setOllamaModels] = useState([])
  const [ollamaRunning, setOllamaRunning] = useState(false)
  const [modelsLoading, setModelsLoading] = useState(false)
  const {
    jobId,
    goal,
    setGoal,
    outputDir,
    setOutputDir,
    modelConfig,
    setModelConfig,
    setCurrentStep,
  } = useMd2LLM()

  useEffect(() => {
    setCurrentStep(2)
  }, [setCurrentStep])

  useEffect(() => {
    let active = true

    async function loadConfigurationState() {
      try {
        const [healthResponse, modelsResponse] = await Promise.all([
          fetch("/api/health"),
          fetch("/api/models"),
        ])

        if (!healthResponse.ok) {
          throw new Error("Health check failed")
        }

        const data = await healthResponse.json()
        let nextModels = []
        let nextOllamaRunning = false
        if (modelsResponse.ok) {
          const modelsData = await modelsResponse.json()
          nextModels = Array.isArray(modelsData.models)
            ? modelsData.models.filter((model) => model.source === "ollama")
            : []
          nextOllamaRunning = Boolean(modelsData.ollama_running)
        }

        if (active) {
          setServerOpenAIKeySet(Boolean(data.openai_key_set))
          setOllamaModels(nextModels)
          setOllamaRunning(nextOllamaRunning)

          if (
            modelConfig.provider === "ollama" &&
            !modelConfig.model &&
            nextModels.length > 0
          ) {
            setModelConfig((current) => ({
              ...current,
              model: nextModels[0].model_name || nextModels[0].name,
            }))
          }
        }
      } catch {
        if (active) {
          setServerOpenAIKeySet(false)
          setOllamaModels([])
          setOllamaRunning(false)
        }
      } finally {
        if (active) {
          setModelsLoading(false)
        }
      }
    }

    setModelsLoading(true)
    loadConfigurationState()
    return () => {
      active = false
    }
  }, [modelConfig.provider, setModelConfig])

  if (!jobId) {
    return <Navigate to="/" replace />
  }

  async function testConnection() {
    setConnectionMessage("")
    setError("")

    try {
      const response = await fetch("/api/health")
      const data = await response.json()

      if (modelConfig.provider === "openai") {
        setServerOpenAIKeySet(Boolean(data.openai_key_set))
        setConnectionMessage(
          data.openai_key_set
            ? "Server can access an OpenAI-compatible API key. Manual entry is optional."
            : "API key is not set in the server environment.",
        )
      } else {
        const ollamaResponse = await fetch("/api/models/ollama-status")
        if (!ollamaResponse.ok) {
          throw new Error("Unable to reach API")
        }
        const ollamaData = await ollamaResponse.json()
        setConnectionMessage(ollamaData.message || "Ollama status checked.")
      }
    } catch {
      setError("Unable to reach the API server.")
    }
  }

  function handleContinue() {
    setError("")
    if (!outputDir.trim()) {
      setError("Choose an output folder for the generated training data.")
      return
    }
    if (
      modelConfig.provider === "openai" &&
      !serverOpenAIKeySet &&
      !modelConfig.apiKey.trim()
    ) {
      setError("An API key is required unless it is already configured on the server.")
      return
    }
    navigate("/review")
  }

  return (
    <Layout currentStep={2}>
      <div className="space-y-5">
        <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
          <section className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <h2 className="text-xl font-semibold text-zinc-100">Training goal</h2>
            <p className="mt-2 text-sm text-zinc-400">
              Choose what kind of supervised pairs should be generated from the vault.
            </p>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              {goals.map((option) => {
                const selected = option.id === goal
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setGoal(option.id)}
                    className={[
                      "rounded-xl border p-5 text-left transition-all duration-150",
                      selected
                        ? "border-brand-600 bg-brand-600/10"
                        : "border-zinc-700 bg-zinc-900 hover:border-zinc-500",
                    ].join(" ")}
                  >
                    <div className="mb-4 text-brand-400">{option.icon}</div>
                    <h3 className="font-medium text-zinc-100">{option.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-zinc-400">{option.description}</p>
                  </button>
                )
              })}
            </div>
          </section>

          <section className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <h2 className="text-xl font-semibold text-zinc-100">
              Which model generates your training data?
            </h2>

            <div className="mt-5 flex rounded-lg border border-zinc-700/50 bg-zinc-800 p-1">
              {[
                { id: "openai", label: "OpenAI-compatible" },
                { id: "ollama", label: "Ollama" },
              ].map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() =>
                    setModelConfig((current) => ({
                      ...current,
                      provider: option.id,
                      model:
                        option.id === "openai"
                          ? current.model && current.provider === "openai"
                            ? current.model
                            : "gpt-4o-mini"
                          : ollamaModels[0]?.model_name || ollamaModels[0]?.name || "",
                    }))
                  }
                  className={[
                    "flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    modelConfig.provider === option.id
                      ? "bg-brand-600 text-white"
                      : "text-zinc-400 hover:text-zinc-200",
                  ].join(" ")}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <div className="mt-5 space-y-4">
              {modelConfig.provider === "openai" ? (
                <>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-zinc-300">API Key</label>
                    <input
                      value={modelConfig.apiKey}
                      onChange={(event) =>
                        setModelConfig((current) => ({ ...current, apiKey: event.target.value }))
                      }
                      placeholder={serverOpenAIKeySet ? "Optional if already configured" : "Paste your API key"}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
                    />
                    <p className="mt-2 text-xs text-zinc-500">
                      {serverOpenAIKeySet
                        ? "The server already has a compatible API key configured. You can leave this blank."
                        : "Paste the API key for your OpenAI-compatible provider."}
                    </p>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-zinc-300">Model</label>
                    <input
                      value={modelConfig.model}
                      onChange={(event) =>
                        setModelConfig((current) => ({ ...current, model: event.target.value }))
                      }
                      placeholder="gpt-4o-mini"
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="rounded-lg border border-zinc-700/50 bg-zinc-800/60 p-4 text-sm text-zinc-300">
                    {ollamaRunning
                      ? "Ollama is running. Pick a model below or type one manually."
                      : "Ollama is not running. You can still type a model name manually."}
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-zinc-300">
                      Detected Ollama models
                    </label>
                    <select
                      value={ollamaModels.some((model) => (model.model_name || model.name) === modelConfig.model) ? modelConfig.model : ""}
                      onChange={(event) =>
                        setModelConfig((current) => ({ ...current, model: event.target.value }))
                      }
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
                    >
                      <option value="">
                        {modelsLoading ? "Loading Ollama models..." : "No selection"}
                      </option>
                      {ollamaModels.map((model) => {
                        const value = model.model_name || model.name
                        return (
                          <option key={model.id} value={value}>
                            {model.name}
                          </option>
                        )
                      })}
                    </select>
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-medium text-zinc-300">Model name</label>
                    <input
                      value={modelConfig.model}
                      onChange={(event) =>
                        setModelConfig((current) => ({ ...current, model: event.target.value }))
                      }
                      placeholder="llama3.2"
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
                    />
                  </div>
                </>
              )}

              <button
                type="button"
                onClick={testConnection}
                className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
              >
                {modelConfig.provider === "openai" ? "Test Connection" : "Check Ollama"}
              </button>

              {connectionMessage ? <p className="text-sm text-zinc-400">{connectionMessage}</p> : null}

              <div className="rounded-xl border border-brand-600/20 bg-brand-600/10 p-4 text-sm text-zinc-300">
                Your API key stays on your machine and is only used for local generation.
              </div>
            </div>

            {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}
          </section>
        </div>

        <section className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
          <h2 className="text-xl font-semibold text-zinc-100">Configuration</h2>
          <p className="mt-2 text-sm text-zinc-400">
            Choose where the generated dataset should be written.
          </p>

          <div className="mt-5 rounded-xl border border-zinc-700/50 bg-zinc-950/60 p-4">
            <h3 className="text-sm font-medium text-zinc-100">Output folder</h3>
            <p className="mt-2 text-sm leading-6 text-zinc-400">
              Choose the folder on this machine where the training JSONL should be written.
            </p>
            <input
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              placeholder="Choose where the generated JSONL should be written"
              className="mt-4 w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setOutputDir("output")}
                className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
              >
                Use project output/
              </button>
            </div>
            <div className="mt-3 rounded-xl border border-zinc-700/50 bg-zinc-900/80 p-4 text-sm text-zinc-400">
              Browsers do not expose an absolute folder path from a folder picker. Enter the
              destination folder path directly, or use the project <span className="font-mono">output/</span> folder.
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between">
            <button
              type="button"
              onClick={() => navigate("/")}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
            >
              ← Back
            </button>
            <button
              type="button"
              onClick={handleContinue}
              className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800"
            >
              Continue →
            </button>
          </div>
        </section>
      </div>
    </Layout>
  )
}
