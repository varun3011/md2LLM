import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"

import { useMd2LLM } from "../App"
import ChatMessage from "../components/ChatMessage"
import Layout from "../components/Layout"

async function readResponse(response) {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

export default function Chat() {
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState("")
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [importingModelId, setImportingModelId] = useState("")
  const [importMessage, setImportMessage] = useState("")
  const [error, setError] = useState("")
  const bottomRef = useRef(null)
  const { setCurrentStep } = useMd2LLM()

  useEffect(() => {
    setCurrentStep(4)
  }, [setCurrentStep])

  async function loadModels(active = true) {
    try {
      const response = await fetch("/api/models")
      if (!response.ok) {
        throw new Error("Failed to load models")
      }
      const data = await response.json()
      const nextModels = data.models || []
      if (active) {
        setModels(nextModels)
        setSelectedModel((current) =>
          nextModels.some((model) => model.ready && model.name === current)
            ? current
            : nextModels.find((model) => model.ready)?.name || "",
        )
      }
    } catch (loadError) {
      if (active) {
        setError(loadError.message)
      }
    }
  }

  useEffect(() => {
    let active = true

    void loadModels(active)
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  async function sendMessage() {
    if (!input.trim() || !selectedModel) {
      return
    }

    const outgoing = input.trim()
    setInput("")
    setLoading(true)
    setError("")
    setMessages((current) => [...current, { role: "user", content: outgoing }])

    try {
      const formData = new FormData()
      formData.append("message", outgoing)
      formData.append("model_name", selectedModel)

      const response = await fetch("/api/chat", {
        method: "POST",
        body: formData,
      })

      const data = await readResponse(response)
      if (!response.ok) {
        throw new Error(data.detail || "Chat failed")
      }

      setMessages((current) => [
        ...current,
        {
          role: "model",
          content: data.response,
          inferenceLogId: data.inference_log_id,
          feedback: "",
        },
      ])
    } catch (chatError) {
      setError(chatError.message)
    } finally {
      setLoading(false)
    }
  }

  async function importIntoOllama(model) {
    setImportingModelId(model.id)
    setImportMessage("")
    setError("")

    const formData = new FormData()
    formData.append("model_path", model.path)
    formData.append("model_name", model.model_name || model.name)

    try {
      const response = await fetch("/api/models/import-ollama", {
        method: "POST",
        body: formData,
      })
      const data = await readResponse(response)
      if (!response.ok) {
        throw new Error(data.detail || "Import failed")
      }
      setImportMessage(data.message || "Model imported into Ollama")
      await loadModels()
      setSelectedModel(data.model_name || model.model_name || model.name)
    } catch (importError) {
      setError(importError.message)
    } finally {
      setImportingModelId("")
    }
  }

  const importableModels = models.filter((model) => model.source === "local" && !model.ready && model.path)
  const chatModels = models.filter((model) => model.ready)

  return (
    <Layout currentStep={4}>
      <div className="space-y-6">
        <div className="flex flex-col gap-4 rounded-xl border border-zinc-700/50 bg-zinc-900 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Chat</h1>
            <p className="mt-2 text-sm text-zinc-400">Talk to a local `.gguf` model through Ollama.</p>
          </div>
          {chatModels.length > 0 ? (
            <select
              value={selectedModel}
              onChange={(event) => setSelectedModel(event.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
            >
              {chatModels.map((model) => (
                <option key={model.id || model.name} value={model.name}>
                  {model.name} ({model.size_mb} MB)
                </option>
              ))}
            </select>
          ) : null}
        </div>

        {error ? <p className="rounded-lg border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">{error}</p> : null}

        {models.length === 0 ? (
          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
            <p className="text-sm text-zinc-400">
              No models found. Complete the training step first.
            </p>
            <Link
              to="/generate"
              className="mt-4 inline-flex rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800"
            >
              Back to generate
            </Link>
          </div>
        ) : (
          <>
            {importableModels.length ? (
              <div className="rounded-xl border border-amber-700/40 bg-amber-950/20 p-4">
                <p className="text-sm font-medium text-amber-200">Local models not imported into Ollama</p>
                <div className="mt-3 space-y-2">
                  {importableModels.map((model) => (
                    <div
                      key={model.id}
                      className="flex flex-col gap-3 rounded-lg border border-amber-800/40 bg-zinc-950/40 p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div>
                        <p className="text-sm font-medium text-zinc-100">{model.name}</p>
                        <p className="mt-1 text-xs text-zinc-500">{model.size_mb} MB</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => importIntoOllama(model)}
                        disabled={Boolean(importingModelId)}
                        className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {importingModelId === model.id ? "Importing..." : "Import into Ollama"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {importMessage ? (
              <p className="rounded-lg border border-emerald-800 bg-emerald-950/40 p-3 text-sm text-emerald-300">
                {importMessage}
              </p>
            ) : null}

            {chatModels.length === 0 ? (
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
                <p className="text-sm text-zinc-400">
                  No models are ready in Ollama yet. Import a local model first.
                </p>
              </div>
            ) : (
              <>
                <div className="h-[28rem] space-y-4 overflow-y-auto rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
              {messages.length === 0 ? (
                <p className="text-sm text-zinc-500">Ask your model anything.</p>
              ) : (
                messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className="space-y-2">
                    <ChatMessage role={message.role === "model" ? "assistant" : "user"} content={message.content} />
                    {message.role === "model" && message.inferenceLogId ? (
                      <div className="flex justify-end gap-2">
                        {["up", "down", "flagged"].map((value) => (
                          <button
                            key={value}
                            type="button"
                            onClick={() => sendFeedback(index, value)}
                            className={[
                              "rounded border px-2 py-1 text-xs transition-colors",
                              message.feedback === value
                                ? "border-brand-500 bg-brand-600/20 text-brand-200"
                                : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:text-zinc-200",
                            ].join(" ")}
                          >
                            {value === "up" ? "Good" : value === "down" ? "Bad" : "Flag"}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
              {loading ? (
                <div className="flex justify-start">
                  <div className="rounded-xl rounded-bl-sm border border-zinc-700 bg-zinc-800 px-4 py-3">
                    <div className="flex gap-1">
                      {[0, 1, 2].map((dot) => (
                        <span
                          key={dot}
                          className="h-2 w-2 animate-bounce rounded-full bg-zinc-400"
                          style={{ animationDelay: `${dot * 0.12}s` }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
              <div ref={bottomRef} />
                </div>

                <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
              <div className="flex gap-3">
                <input
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault()
                      sendMessage()
                    }
                  }}
                  placeholder="Ask your model anything..."
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={sendMessage}
                  disabled={loading}
                  className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:opacity-50"
                >
                  Send
                </button>
              </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Layout>
  )

  async function sendFeedback(index, feedback) {
    const message = messages[index]
    if (!message?.inferenceLogId) return

    const formData = new FormData()
    formData.append("feedback", feedback)
    formData.append("flagged", feedback === "flagged" ? "true" : "false")

    try {
      const response = await fetch(`/api/registry/inference-logs/${message.inferenceLogId}/feedback`, {
        method: "POST",
        body: formData,
      })
      const data = await readResponse(response)
      if (!response.ok) throw new Error(data.detail || "Failed to save feedback")
      setMessages((current) =>
        current.map((item, itemIndex) =>
          itemIndex === index ? { ...item, feedback } : item,
        ),
      )
    } catch (feedbackError) {
      setError(feedbackError.message)
    }
  }
}
