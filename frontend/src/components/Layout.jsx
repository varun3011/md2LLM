import { useEffect, useState } from "react"
import { Link } from "react-router-dom"

import StepIndicator from "./StepIndicator"

export default function Layout({ currentStep, children, contentClassName = "max-w-4xl" }) {
  const [apiConnected, setApiConnected] = useState(null)

  useEffect(() => {
    let active = true

    async function checkHealth() {
      try {
        const response = await fetch("/api/health")
        if (!response.ok) {
          throw new Error("Health check failed")
        }
        if (active) {
          setApiConnected(true)
        }
      } catch {
        if (active) {
          setApiConnected(false)
        }
      }
    }

    checkHealth()
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="min-h-screen bg-transparent">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 pb-10 pt-6 sm:px-6 lg:px-8">
        <header className="mb-8 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-zinc-700/50 bg-zinc-900">
              <div className="h-4 w-4 rounded-full bg-gradient-to-br from-brand-300 to-brand-800 shadow-[0_0_18px_rgba(16,185,129,0.45)]" />
            </div>
            <div>
              <p className="text-lg font-semibold tracking-tight text-zinc-100">md2LLM</p>
              <p className="text-xs text-zinc-500">Your notes, trained into a model.</p>
            </div>
          </Link>

          <div
            className="flex items-center gap-2 rounded-full border border-zinc-700/50 bg-zinc-900 px-3 py-1.5 text-sm text-zinc-400"
            title={apiConnected ? "API connected" : "API offline"}
          >
            <span
              className={[
                "h-2.5 w-2.5 rounded-full",
                apiConnected === null
                  ? "bg-zinc-600"
                  : apiConnected
                    ? "bg-emerald-400"
                    : "bg-red-500",
              ].join(" ")}
            />
            <span>{apiConnected ? "API online" : apiConnected === false ? "API offline" : "Checking API"}</span>
          </div>
        </header>

        <StepIndicator currentStep={currentStep} />

        <main className={`mx-auto mt-8 w-full flex-1 transition-opacity duration-200 ${contentClassName}`}>
          {children}
        </main>
      </div>
    </div>
  )
}
