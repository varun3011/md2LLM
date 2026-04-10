import { useEffect, useRef, useState } from "react"

export default function DepsCheck({ approach, onReady }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [installState, setInstallState] = useState(null)
  const [checking, setChecking] = useState(false)
  const logRef = useRef(null)
  const esRef = useRef(null)

  useEffect(() => {
    void checkDeps()
    return () => {
      if (esRef.current) esRef.current.close()
    }
  }, [approach])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [installState?.log])

  async function checkDeps() {
    setLoading(true)
    setChecking(false)
    try {
      const res = await fetch(`/api/training/check-deps?approach=${encodeURIComponent(approach)}`)
      const data = await res.json()
      setStatus(data)

      if (data.ready) {
        setTimeout(() => onReady(), 800)
      }
    } catch (error) {
      console.error("Dep check failed", error)
    }
    setLoading(false)
  }

  async function handleAutoInstall() {
    setInstalling(true)
    setInstallState({
      status: "running",
      progress: 0,
      message: "Starting installation...",
      log: [],
    })

    try {
      const form = new FormData()
      form.append("approach", approach)

      const res = await fetch("/api/training/install-deps", {
        method: "POST",
        body: form,
      })
      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || "Failed to start dependency install")
      }

      const es = new EventSource(`/api/training/install-status/${data.install_job_id}`)
      esRef.current = es

      es.onmessage = (event) => {
        const state = JSON.parse(event.data)
        setInstallState(state)

        if (state.status === "complete") {
          es.close()
          setTimeout(() => {
            setInstalling(false)
            void checkDeps()
          }, 1000)
        } else if (state.status === "error") {
          es.close()
          setInstalling(false)
        }
      }

      es.onerror = () => {
        es.close()
        setInstalling(false)
      }
    } catch (error) {
      setInstallState((prev) => ({
        ...(prev || {}),
        status: "error",
        error: error.message,
        message: `Installation failed: ${error.message}`,
      }))
      setInstalling(false)
    }
  }

  async function handleCheckAgain() {
    setChecking(true)
    await checkDeps()
    setChecking(false)
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
          <p className="text-sm text-zinc-400">Checking training dependencies...</p>
        </div>
      </div>
    )
  }

  if (status?.colab_required) {
    return null
  }

  if (status?.ready && !installing) {
    return (
      <div className="rounded-xl border border-green-700/30 bg-green-900/10 p-5">
        <div className="flex items-center gap-3">
          <span className="text-lg text-green-400">✓</span>
          <div>
            <p className="text-sm font-medium text-zinc-200">Training dependencies ready</p>
            <p className="mt-0.5 text-xs text-zinc-500">{status.message}</p>
          </div>
        </div>
      </div>
    )
  }

  if (approach === "mlx") {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
          <div className="mb-4 flex items-start justify-between">
            <div>
              <p className="mb-1 font-medium text-zinc-100">MLX required for Apple Silicon training</p>
              <p className="text-sm text-zinc-400">Apple's framework for fast local training on M1/M2/M3</p>
            </div>
            <span className="rounded-full bg-zinc-800 px-2 py-1 text-xs text-zinc-300">Apple Silicon</span>
          </div>

          <div className="mb-4 space-y-2">
            {status?.checks &&
              Object.entries(status.checks).map(([key, done]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className={`text-sm ${done ? "text-green-400" : "text-zinc-600"}`}>
                    {done ? "✓" : "○"}
                  </span>
                  <span className={`text-sm ${done ? "text-zinc-300" : "text-zinc-500"}`}>
                    {key === "apple_silicon" && "Apple Silicon hardware"}
                    {key === "mlx" && "MLX framework"}
                    {key === "mlx_lm" && "MLX-LM language model tools"}
                    {key === "python_runtime" && `Python runtime${status?.python_version ? ` (${status.python_version})` : ""}`}
                  </span>
                </div>
              ))}
          </div>

          {status?.setup_steps && !installing && (
            <div className="mb-4 rounded-lg border border-amber-700/30 bg-amber-900/20 p-3">
              <p className="mb-1 text-sm font-medium text-amber-400">Python environment needs to be updated</p>
              <p className="mb-3 text-xs text-zinc-400">{status.message}</p>
              <div className="space-y-2">
                {status.setup_steps.map((step, index) => (
                  <div key={step} className="flex gap-2 text-xs text-zinc-300">
                    <span className="text-amber-400">{index + 1}.</span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
              {status.install_command && (
                <code className="mt-3 block rounded bg-zinc-950 px-3 py-2 font-mono text-xs text-green-400">
                  {status.install_command}
                </code>
              )}
            </div>
          )}

          {!status?.ready && !installing && !status?.setup_steps && (
            <div className="mb-4 grid grid-cols-2 gap-2 rounded-lg bg-zinc-800 p-3 text-sm sm:grid-cols-4">
              <span className="text-zinc-400">Package</span>
              <span className="font-mono text-zinc-200">mlx-lm</span>
              <span className="text-zinc-400">~500 MB</span>
              <span className="text-zinc-400">2-3 minutes</span>
            </div>
          )}

          {!installing && !status?.ready && status?.can_auto_install && (
            <button
              onClick={handleAutoInstall}
              className="w-full rounded-lg bg-brand-600 py-2.5 font-medium text-white transition-colors hover:bg-brand-800"
            >
              Install MLX automatically →
            </button>
          )}

          {!installing && !status?.ready && !status?.can_auto_install && (
            <button
              onClick={handleCheckAgain}
              disabled={checking}
              className="w-full rounded-lg bg-zinc-700 py-2.5 font-medium text-zinc-200 transition-colors hover:bg-zinc-600 disabled:opacity-50"
            >
              {checking ? "Checking..." : "Check again after restarting backend"}
            </button>
          )}
        </div>

        {installing && installState && (
          <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-medium text-zinc-200">{installState.message}</p>
              <span className="text-sm text-zinc-400">{installState.progress}%</span>
            </div>

            <div className="mb-4 h-2 w-full rounded-full bg-zinc-800">
              <div
                className="h-2 rounded-full bg-brand-600 transition-all duration-300"
                style={{ width: `${installState.progress || 0}%` }}
              />
            </div>

            <div ref={logRef} className="h-32 overflow-y-auto rounded-lg bg-zinc-950 p-3 font-mono">
              {installState.log?.map((line, index) => (
                <p key={`${line}-${index}`} className="text-xs text-zinc-400">
                  {line}
                </p>
              ))}
            </div>

            {installState.status === "error" && (
              <div className="mt-3 rounded-lg border border-red-700/30 bg-red-900/20 p-3">
                <p className="mb-1 text-sm font-medium text-red-400">Installation failed</p>
                <p className="mb-2 text-xs text-zinc-400">Try installing manually:</p>
                <code className="block rounded bg-zinc-800 px-2 py-1 text-xs text-green-400">pip install mlx-lm</code>
                <button onClick={handleCheckAgain} className="mt-2 text-xs text-brand-400 hover:text-brand-300">
                  Check again after manual install
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  if (approach === "unsloth" || approach === "unsloth_small") {
    const steps = status?.steps || []
    const doneCount = steps.filter((step) => step.done).length

    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-5">
          <div className="mb-3 flex items-start justify-between">
            <div>
              <p className="mb-1 font-medium text-zinc-100">NVIDIA GPU setup required</p>
              <p className="text-sm text-zinc-400">Unsloth enables fast QLoRA training on NVIDIA GPUs</p>
            </div>
            <span className="rounded-full bg-green-900/30 px-2 py-1 text-xs text-green-400">NVIDIA CUDA</span>
          </div>

          <div className="mb-2 flex items-center gap-2">
            <div className="h-1.5 flex-1 rounded-full bg-zinc-800">
              <div
                className="h-1.5 rounded-full bg-brand-600 transition-all"
                style={{ width: `${steps.length > 0 ? (doneCount / steps.length) * 100 : 0}%` }}
              />
            </div>
            <span className="text-xs text-zinc-500">
              {doneCount}/{steps.length} complete
            </span>
          </div>
        </div>

        <div className="space-y-3">
          {steps.map((step) => (
            <div
              key={step.number}
              className={`rounded-xl border p-4 transition-all ${
                step.done ? "border-green-700/30 bg-green-900/5" : "border-zinc-700/50 bg-zinc-900"
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-medium ${
                    step.done ? "bg-green-700/30 text-green-400" : "bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {step.done ? "✓" : step.number}
                </div>

                <div className="flex-1">
                  <p className={`mb-1 text-sm font-medium ${step.done ? "text-zinc-400" : "text-zinc-200"}`}>
                    {step.title}
                  </p>

                  {step.command && (
                    <div className="group relative mb-2">
                      <code className="block rounded-lg bg-zinc-800 px-3 py-2 font-mono text-xs text-green-400">
                        {step.command}
                      </code>
                      <button
                        onClick={() => navigator.clipboard.writeText(step.command)}
                        className="absolute right-2 top-1.5 text-xs text-zinc-600 opacity-0 transition-opacity hover:text-zinc-300 group-hover:opacity-100"
                      >
                        copy
                      </button>
                    </div>
                  )}

                  {step.note && <p className="text-xs text-zinc-500">{step.note}</p>}
                  {step.expected_output && !step.done && (
                    <p className="mt-1 text-xs text-zinc-600">Expected: {step.expected_output}</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between rounded-xl border border-zinc-700/50 bg-zinc-900 p-4">
          <div>
            <p className="text-sm font-medium text-zinc-300">Done installing?</p>
            <p className="text-xs text-zinc-500">Click below to verify all steps are complete</p>
          </div>
          <button
            onClick={handleCheckAgain}
            disabled={checking}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-800 disabled:opacity-50"
          >
            {checking ? "Checking..." : "Check again"}
          </button>
        </div>

        <p className="text-center text-xs text-zinc-600">
          Having trouble?{" "}
          <a href="/docs/gpu-setup.md" className="text-brand-400 hover:text-brand-300">
            See the full NVIDIA setup guide
          </a>
        </p>
      </div>
    )
  }

  return null
}
