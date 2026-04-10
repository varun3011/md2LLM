export default function ChatMessage({ role, content }) {
  const isUser = role === "user"

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          "max-w-[80%] rounded-xl border px-4 py-3 text-sm leading-6",
          isUser
            ? "rounded-br-sm border-brand-600/30 bg-brand-600/20 text-zinc-100"
            : "rounded-bl-sm border-zinc-700 bg-zinc-800 text-zinc-200",
        ].join(" ")}
      >
        <p className="mb-1 text-xs uppercase tracking-[0.2em] text-zinc-500">
          {isUser ? "You" : "Model"}
        </p>
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  )
}
