import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"

import { useMd2LLM } from "../App"
import ChatMessage from "../components/ChatMessage"
import Layout from "../components/Layout"

export default function Chat() {
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState("")
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const bottomRef = useRef(null)
  const { setCurrentStep } = useMd2LLM()

  useEffect(() => {
    setCurrentStep(4)
  }, [setCurrentStep])

  useEffect(() => {
    let active = true

    async function loadModels() {
      try {
        const response = await fetch("/api/models")
        if (!response.ok) {
          throw new Error("Failed to load models")
        }
        const data = await response.json()
        if (active) {
          setModels(data.models || [])
          setSelectedModel(data.models?.[0]?.name || "")
        }
      } catch (loadError) {
        if (active) {
          setError(loadError.message)
        }
      }
    }

    loadModels()
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

      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || "Chat failed")
      }

      setMessages((current) => [...current, { role: "model", content: data.response }])
    } catch (chatError) {
      setError(chatError.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Layout currentStep={4}>
      <div className="space-y-6">
        <div className="flex flex-col gap-4 rounded-xl border border-zinc-700/50 bg-zinc-900 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Chat</h1>
            <p className="mt-2 text-sm text-zinc-400">Talk to a local `.gguf` model through Ollama.</p>
          </div>
          {models.length > 0 ? (
            <select
              value={selectedModel}
              onChange={(event) => setSelectedModel(event.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
            >
              {models.map((model) => (
                <option key={model.filename} value={model.name}>
                  {model.name} ({model.size_mb} MB)
                </option>
              ))}
            </select>
          ) : null}
        </div>

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
            <div className="h-[28rem] space-y-4 overflow-y-auto rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
              {messages.length === 0 ? (
                <p className="text-sm text-zinc-500">Ask your model anything.</p>
              ) : (
                messages.map((message, index) => (
                  <ChatMessage key={`${message.role}-${index}`} role={message.role === "model" ? "assistant" : "user"} content={message.content} />
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
              {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
            </div>
          </>
        )}
      </div>
    </Layout>
  )
}
