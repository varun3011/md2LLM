import { createContext, useContext, useState } from "react"
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom"

import ConfigureModel from "./pages/ConfigureModel"
import Generate from "./pages/Generate"
import ReviewFiles from "./pages/ReviewFiles"
import SelectModel from "./pages/SelectModel"
import SelectVault from "./pages/SelectVault"
import Chat from "./pages/Chat"
import TrainConfig from "./pages/TrainConfig"
import TrainRun from "./pages/TrainRun"
import Layout from "./components/Layout"

const AppContext = createContext(null)

export function useMd2LLM() {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error("useMd2LLM must be used within AppContext")
  }
  return context
}

function AppProvider({ children }) {
  const [notes, setNotes] = useState([])
  const [vaultStats, setVaultStats] = useState(null)
  const [goal, setGoal] = useState("knowledge")
  const [outputDir, setOutputDir] = useState("")
  const [modelConfig, setModelConfig] = useState({
    provider: "openai",
    model: "gpt-4o-mini",
    apiKey: "",
  })
  const [jobId, setJobId] = useState(null)
  const [currentStep, setCurrentStep] = useState(1)

  const value = {
    notes,
    setNotes,
    vaultStats,
    setVaultStats,
    goal,
    setGoal,
    outputDir,
    setOutputDir,
    modelConfig,
    setModelConfig,
    jobId,
    setJobId,
    currentStep,
    setCurrentStep,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

function TrainPlaceholder() {
  const location = useLocation()
  const selectedModel = location.state?.selectedModel
  const config = location.state?.config

  return (
    <Layout currentStep={4}>
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-900 p-6">
        <h1 className="text-2xl font-semibold text-zinc-100">Training step not built yet</h1>
        <p className="mt-2 text-sm text-zinc-400">
          The training configuration handoff is working. Actual training execution comes in the next step.
        </p>
        {selectedModel ? (
          <p className="mt-4 text-sm text-zinc-300">
            Selected model: <span className="font-medium text-zinc-100">{selectedModel}</span>
          </p>
        ) : null}
        {config?.output_name ? (
          <p className="mt-2 text-sm text-zinc-300">
            Output model: <span className="font-medium text-zinc-100">{config.output_name}</span>
          </p>
        ) : null}
      </div>
    </Layout>
  )
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<SelectVault />} />
          <Route path="/configure" element={<ConfigureModel />} />
          <Route path="/review" element={<ReviewFiles />} />
          <Route path="/generate" element={<Generate />} />
          <Route path="/select-model" element={<SelectModel />} />
          <Route path="/train/config" element={<TrainConfig />} />
          <Route path="/train" element={<TrainPlaceholder />} />
          <Route path="/train/run" element={<TrainRun />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
