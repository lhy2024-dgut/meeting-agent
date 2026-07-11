import { formatTranscriptTime } from "@/lib/format";
import { TranscriptSegment } from "@/types/api";

type TranscriptListProps = {
  segments: TranscriptSegment[];
  highlighted?: boolean;
};

export function TranscriptList({
  segments,
  highlighted = false,
}: TranscriptListProps) {
  if (segments.length === 0) {
    return <div className="empty-inline">暂无转录数据</div>;
  }

  return (
    <div className="space-y-1">
      {segments.map((segment) => (
        <div
          key={segment.id}
          className={
            highlighted
              ? "transcript-line transcript-line-highlighted"
              : "transcript-line"
          }
        >
          <span className="transcript-ts">
            {formatTranscriptTime(segment.start_time)}
          </span>
          {segment.text}
        </div>
      ))}
    </div>
  );
}
