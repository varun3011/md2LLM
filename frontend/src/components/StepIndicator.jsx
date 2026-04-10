const steps = [
  { id: 1, label: "Select Vault" },
  { id: 2, label: "Configuration" },
  { id: 3, label: "Review Files" },
  { id: 4, label: "Generate" },
]

export default function StepIndicator({ currentStep }) {
  return (
    <div className="rounded-2xl border border-zinc-700/50 bg-zinc-900/70 p-4 backdrop-blur">
      <div className="flex items-center justify-between gap-3 overflow-x-auto">
        {steps.map((step, index) => {
          const complete = currentStep > step.id
          const active = currentStep === step.id

          return (
            <div key={step.id} className="flex min-w-max flex-1 items-center gap-3">
              <div className="flex items-center gap-3">
                <div
                  className={[
                    "flex h-9 w-9 items-center justify-center rounded-full border text-sm font-medium transition-all duration-150",
                    complete
                      ? "border-brand-400 bg-brand-400/10 text-brand-400"
                      : active
                        ? "border-brand-600 bg-brand-600 text-white"
                        : "border-zinc-700 bg-zinc-800 text-zinc-500",
                  ].join(" ")}
                >
                  {complete ? "✓" : step.id}
                </div>
                <div>
                  <p
                    className={[
                      "text-sm font-medium",
                      complete || active ? "text-zinc-100" : "text-zinc-600",
                    ].join(" ")}
                  >
                    {step.label}
                  </p>
                </div>
              </div>

              {index < steps.length - 1 ? (
                <div className="h-px flex-1 bg-zinc-800" />
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
