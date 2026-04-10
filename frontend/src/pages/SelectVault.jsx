import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"

import Layout from "../components/Layout"
import { useMd2LLM } from "../App"

export default function SelectVault() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)
  const folderInputRef = useRef(null)
  const trainingFileInputRef = useRef(null)
  const [pathInput, setPathInput] = useState("")
  const [error, setError] = useState("")
  const [isUploading, setIsUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const { goal, setVaultStats, setCurrentStep, setNotes, setJobId } = useMd2LLM()

  useEffect(() => {
    setCurrentStep(1)
  }, [setCurrentStep])

  const uploadZoneClass = [
    "group rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-150",
    dragActive
      ? "border-brand-600 bg-brand-600/5"
      : "border-zinc-700 bg-zinc-900 hover:border-brand-600 hover:bg-brand-600/5",
  ].join(" ")

  async function checkServer() {
    const response = await fetch("/api/health")
    if (!response.ok) {
      throw new Error("API not running")
    }
    return response.json()
  }

  function finalizeVaultSelection(data) {
    setJobId(data.job_id)
    setVaultStats({
      total_found: data.md_files_found,
      passed_filter: data.md_files_found,
    })
    setNotes([])
    navigate("/configure")
  }

  function finalizeTrainingDataSelection(data) {
    setJobId(data.job_id)
    setVaultStats(null)
    setNotes([])
    navigate("/select-model", {
      state: {
        goal,
        jobId: data.job_id,
        pairsCount: data.pair_count,
      },
    })
  }

  async function handleZipUpload(file) {
    if (!file) {
      return
    }

    setError("")
    setIsUploading(true)

    try {
      const formData = new FormData()
      formData.append("file", file)
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || "Upload failed")
      }

      const data = await response.json()
      finalizeVaultSelection(data)
    } catch (uploadError) {
      setError(uploadError.message)
    } finally {
      setIsUploading(false)
    }
  }

  async function handleFolderUpload(fileList) {
    const files = Array.from(fileList || [])
    if (files.length === 0) {
      return
    }

    setError("")
    setIsUploading(true)

    try {
      const formData = new FormData()
      for (const file of files) {
        const relativePath = file.webkitRelativePath || file.name
        formData.append("files", file, relativePath)
      }

      const response = await fetch("/api/upload-folder", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || "Folder upload failed")
      }

      const data = await response.json()
      finalizeVaultSelection(data)
    } catch (uploadError) {
      setError(uploadError.message)
    } finally {
      setIsUploading(false)
    }
  }

  async function handleTrainingDataUpload(file) {
    if (!file) {
      return
    }

    setError("")
    setIsUploading(true)

    try {
      const formData = new FormData()
      formData.append("file", file)

      const response = await fetch("/api/upload-training-data", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || "Training data upload failed")
      }

      const data = await response.json()
      finalizeTrainingDataSelection(data)
    } catch (uploadError) {
      setError(uploadError.message)
    } finally {
      setIsUploading(false)
    }
  }

  async function handlePathSubmit(event) {
    event.preventDefault()
    setError("")

    if (!pathInput.trim()) {
      setError("Enter a vault path first.")
      return
    }

    try {
      await checkServer()
      const formData = new FormData()
      formData.append("vault_path", pathInput.trim())

      const response = await fetch("/api/register-vault", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || "Failed to register vault path")
      }

      const data = await response.json()
      setVaultStats(null)
      setNotes([])
      finalizeVaultSelection(data)
    } catch (submitError) {
      setError(
        submitError.message ||
          "API not running. Start it with: uvicorn server.app:app --host 127.0.0.1 --port 8000",
      )
    }
  }

  return (
    <Layout currentStep={1}>
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="w-full rounded-3xl border border-zinc-700/50 bg-zinc-900 p-8 shadow-2xl shadow-black/20">
          <div className="mb-10 text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-zinc-700/50 bg-zinc-800">
              <div className="h-7 w-7 rounded-full bg-gradient-to-br from-brand-300 to-brand-800 shadow-[0_0_28px_rgba(16,185,129,0.45)]" />
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-zinc-100">md2LLM</h1>
            <p className="mt-3 text-base text-zinc-400">
              Turn your notes into your personal model
            </p>
          </div>

          <div
            className={uploadZoneClass}
            onDragEnter={(event) => {
              event.preventDefault()
              setDragActive(true)
            }}
            onDragOver={(event) => {
              event.preventDefault()
              setDragActive(true)
            }}
            onDragLeave={(event) => {
              event.preventDefault()
              setDragActive(false)
            }}
            onDrop={(event) => {
              event.preventDefault()
              setDragActive(false)
              const droppedFiles = event.dataTransfer.files
              if (!droppedFiles || droppedFiles.length === 0) {
                return
              }

              const hasFolderEntries = Array.from(droppedFiles).some((file) =>
                Boolean(file.webkitRelativePath),
              )

              if (droppedFiles.length > 1 || hasFolderEntries) {
                handleFolderUpload(droppedFiles)
                return
              }

              const [firstFile] = droppedFiles
              if (firstFile.name.toLowerCase().endsWith(".zip")) {
                handleZipUpload(firstFile)
                return
              }
              if (firstFile.name.toLowerCase().endsWith(".jsonl")) {
                handleTrainingDataUpload(firstFile)
                return
              }

              setError("Drop a vault folder, a .zip archive, or a training_data.jsonl file.")
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(event) => handleZipUpload(event.target.files?.[0])}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              webkitdirectory=""
              directory=""
              className="hidden"
              onChange={(event) => handleFolderUpload(event.target.files)}
            />
            <input
              ref={trainingFileInputRef}
              type="file"
              accept=".jsonl,application/jsonl"
              className="hidden"
              onChange={(event) => handleTrainingDataUpload(event.target.files?.[0])}
            />
            <div className="space-y-4">
              <p className="text-lg font-medium text-zinc-100">
                {isUploading ? "Uploading..." : "Drop your vault or training file here"}
              </p>
              <p className="text-sm text-zinc-400">
                or click below to select a vault folder, a zip file, or an existing training file
              </p>
              <p className="font-mono text-xs uppercase tracking-[0.2em] text-zinc-500">
                Accepts: vault folder, .zip vault, or training_data.jsonl
              </p>
              <div className="flex flex-col justify-center gap-3 pt-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800"
                >
                  Select Folder
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
                >
                  Select Zip
                </button>
                <button
                  type="button"
                  onClick={() => trainingFileInputRef.current?.click()}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
                >
                  Upload Training File
                </button>
              </div>
            </div>
          </div>

          <div className="mt-6 rounded-2xl border border-zinc-700/50 bg-zinc-950/60 p-5">
            <p className="text-sm font-medium text-zinc-100">Already have training data?</p>
            <p className="mt-2 text-sm leading-6 text-zinc-400">
              Upload an existing <span className="font-mono text-zinc-300">training_data.jsonl</span> file to skip
              vault review and pair generation, then go straight to model selection.
            </p>
          </div>

          <div className="my-8 flex items-center gap-4">
            <div className="h-px flex-1 bg-zinc-800" />
            <span className="text-sm text-zinc-600">or</span>
            <div className="h-px flex-1 bg-zinc-800" />
          </div>

          <form onSubmit={handlePathSubmit} className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-zinc-300">
                Enter vault path on this machine
              </label>
              <input
                value={pathInput}
                onChange={(event) => setPathInput(event.target.value)}
                placeholder="Path to your vault folder"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-zinc-100 focus:border-brand-600 focus:outline-none"
              />
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                className="rounded-lg bg-brand-600 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800"
              >
                Use Path →
              </button>
            </div>
          </form>

          {error ? <p className="mt-4 text-sm text-red-400">{error}</p> : null}

          <p className="mt-8 text-center text-sm text-zinc-500">
            Obsidian vault? You can now select the folder directly or upload a zip.
          </p>
        </div>
      </div>
    </Layout>
  )
}
