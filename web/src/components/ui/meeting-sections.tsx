import ReactMarkdown from "react-markdown";

export function TodoSection({ text }: { text: string }) {
  const items = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) =>
      line.replace(/^- \[ \] /, "").replace(/^- /, "").replace(/^• /, ""),
    );

  if (items.length === 0) {
    return <div className="empty-inline">本次会议未明确待办事项</div>;
  }

  return (
    <div className="space-y-1">
      {items.map((item, index) => {
        const [desc, ...metaParts] = item.split("|").map((part) => part.trim());
        const meta = metaParts.filter(Boolean).join(" · ");
        return (
          <div key={`${item}-${index}`} className="todo-item">
            <div className="todo-dot" />
            <div className="todo-content">
              <div className="todo-text">{desc}</div>
              {meta ? <div className="todo-meta">{meta}</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ResolutionSection({ text }: { text: string }) {
  const items = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !line.startsWith("## ") && !line.startsWith("### "))
    .map((line) =>
      line
        .replace(/^\d+[\.)、]\s*/, "")
        .replace(/^- /, "")
        .replace(/^• /, "")
        .replace(/\*\*(.*?)\*\*/g, "$1")
        .trim(),
    )
    .filter(Boolean);

  if (items.length === 0) {
    return <div className="empty-inline">本次会议未明确决议</div>;
  }

  return (
    <div className="space-y-3">
      {items.map((item, index) => (
        <div key={`${item}-${index}`} className="decision-item">
          <div className="decision-number">决议 {index + 1}</div>
          <div className="decision-text">{item}</div>
        </div>
      ))}
    </div>
  );
}

export function MinutesPaper({ text }: { text: string }) {
  if (!text.trim()) {
    return <div className="empty-inline">纪要内容为空，请检查音频质量或重试。</div>;
  }

  return (
    <div className="minutes-paper">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}

