export default function ProgressBar({ value, total }) {
  const percentage = total > 0 ? Math.min(100, (value / total) * 100) : 0

  return (
    <div className="space-y-3">
      <div className="h-3 rounded-full bg-zinc-800">
        <div
          className="h-3 rounded-full bg-brand-600 transition-all duration-500 ease-out"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-sm text-zinc-400">
        <span>{value} completed</span>
        <span>{total} total</span>
      </div>
    </div>
  )
}
