"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { fetchMeetingAudioObjectUrl } from "@/lib/api";
import { formatTranscriptTime } from "@/lib/format";
import { TranscriptSegment } from "@/types/api";

type TranscriptPlayerProps = {
  meetingId: number;
  segments: TranscriptSegment[];
  highlighted?: boolean;
};

// 一个说话人的连续发言合并成一个块，每块对应一个时间戳（说话人切换处）
type SpeakerBlock = {
  key: string;
  speaker: string;
  start: number;
  end: number;
  text: string;
};

// 说话人标识配色（按出现顺序循环分配），与实时转写一致地用颜色区分说话人
const SPEAKER_COLORS = [
  "#6366f1", // 靛蓝
  "#10b981", // 翠绿
  "#f59e0b", // 琥珀
  "#ef4444", // 红
  "#0ea5e9", // 天蓝
  "#a855f7", // 紫
  "#ec4899", // 粉
  "#14b8a6", // 青
];

// 同一说话人的连续发言合并到一个块，但单块超过该字数后另起新块（在句子边界切分，
// 因为每个 segment 本身就是一句话，不会从句子中间切）。
const MAX_TURN_CHARS = 100;

function groupBySpeaker(segments: TranscriptSegment[]): SpeakerBlock[] {
  const blocks: SpeakerBlock[] = [];
  for (const segment of segments) {
    const speaker = segment.speaker || "";
    const last = blocks[blocks.length - 1];
    // 仅合并「相邻、同一非空说话人、且当前块未超过 100 字」的分句；
    // 无说话人数据时逐段保留，避免塌成一大段
    if (last && speaker && last.speaker === speaker && last.text.length < MAX_TURN_CHARS) {
      last.text = `${last.text}${segment.text}`;
      last.end = segment.end_time;
      continue;
    }
    blocks.push({
      key: `${segment.id}`,
      speaker,
      start: segment.start_time,
      end: segment.end_time,
      text: segment.text,
    });
  }
  return blocks;
}

export function TranscriptPlayer({
  meetingId,
  segments,
  highlighted = false,
}: TranscriptPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // 点击时间戳后，播放到该值（秒）自动暂停；null 表示连续播放
  const playUntilRef = useRef<number | null>(null);

  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioError, setAudioError] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  // 先按时间戳升序排序，再按说话人分块（FunASR 说话人识别返回的分句顺序不保证按时间）
  const blocks = useMemo(() => {
    const ordered = [...segments].sort(
      (a, b) => a.start_time - b.start_time || a.end_time - b.end_time,
    );
    return groupBySpeaker(ordered);
  }, [segments]);

  // 说话人 → 颜色映射（按首次出现顺序分配）
  const speakerColors = useMemo(() => {
    const map = new Map<string, string>();
    for (const block of blocks) {
      if (block.speaker && !map.has(block.speaker)) {
        map.set(block.speaker, SPEAKER_COLORS[map.size % SPEAKER_COLORS.length]);
      }
    }
    return map;
  }, [blocks]);

  // 加载录音（一次性取回 blob，转 object URL）
  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    fetchMeetingAudioObjectUrl(meetingId)
      .then((url) => {
        if (revoked) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setAudioUrl(url);
      })
      .catch((error) => {
        setAudioError(error instanceof Error ? error.message : "录音加载失败");
      });
    return () => {
      revoked = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [meetingId]);

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      playUntilRef.current = null; // 手动播放取消区间限制
      void audio.play();
    } else {
      audio.pause();
    }
  }

  function handleSeek(event: React.ChangeEvent<HTMLInputElement>) {
    const audio = audioRef.current;
    if (!audio) return;
    playUntilRef.current = null; // 拖动进度条取消区间限制
    const next = Number(event.target.value);
    audio.currentTime = next;
    setCurrentTime(next);
  }

  // 点击某段时间戳：跳转到该段起点，播放到下一段起点（末段播放到本段结束）
  function playBlock(index: number) {
    const audio = audioRef.current;
    if (!audio) return;
    const block = blocks[index];
    const next = blocks[index + 1];
    const stopAt = next ? next.start : block.end || duration;
    playUntilRef.current = stopAt;
    setActiveKey(block.key);
    audio.currentTime = block.start;
    setCurrentTime(block.start);
    void audio.play();
  }

  function handleTimeUpdate() {
    const audio = audioRef.current;
    if (!audio) return;
    const now = audio.currentTime;
    setCurrentTime(now);
    const stopAt = playUntilRef.current;
    if (stopAt !== null && now >= stopAt) {
      audio.pause();
      playUntilRef.current = null;
    }
  }

  return (
    <div className="space-y-4">
      {/* ── 录音播放器 ── */}
      <div className="transcript-player">
        {audioError ? (
          <div className="text-[13px] text-[var(--muted)]">
            {"录音不可用："}
            {audioError}
          </div>
        ) : !audioUrl ? (
          <div className="text-[13px] text-[var(--muted)]">{"录音加载中…"}</div>
        ) : (
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="transcript-play-btn"
              onClick={togglePlay}
              aria-label={isPlaying ? "暂停" : "播放"}
            >
              {isPlaying ? "❚❚" : "▶"}
            </button>
            <span className="transcript-ts tabular-nums">
              {formatTranscriptTime(currentTime)}
            </span>
            <input
              type="range"
              className="transcript-range"
              min={0}
              max={duration || 0}
              step={0.01}
              value={Math.min(currentTime, duration || 0)}
              onChange={handleSeek}
              aria-label="播放进度"
            />
            <span className="transcript-ts tabular-nums">
              {formatTranscriptTime(duration)}
            </span>
          </div>
        )}
        {audioUrl ? (
          <audio
            ref={audioRef}
            src={audioUrl}
            preload="metadata"
            onLoadedMetadata={(event) => setDuration(event.currentTarget.duration || 0)}
            onTimeUpdate={handleTimeUpdate}
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => setIsPlaying(false)}
            className="hidden"
          />
        ) : null}
      </div>

      {/* ── 按说话人分段的转录 ── */}
      {blocks.length === 0 ? (
        <div className="empty-inline">{"暂无转录数据"}</div>
      ) : (
        <div className="space-y-3">
          {blocks.map((block, index) => {
            const color = block.speaker ? speakerColors.get(block.speaker) : null;
            const isActive = activeKey === block.key;
            return (
              <div
                key={block.key}
                className={
                  highlighted
                    ? "transcript-turn transcript-line transcript-line-highlighted"
                    : isActive
                      ? "transcript-turn transcript-line transcript-line-active"
                      : "transcript-turn transcript-line"
                }
                style={color ? { borderLeftColor: color } : undefined}
              >
                {/* 时间戳：单独一行，放在说话人标识上方，可点击跳转播放 */}
                <button
                  type="button"
                  className="transcript-ts-btn"
                  onClick={() => playBlock(index)}
                  title="从此处播放到下一段"
                  disabled={!audioUrl}
                >
                  {formatTranscriptTime(block.start)}
                </button>
                {block.speaker ? (
                  <div
                    className="transcript-speaker"
                    style={
                      color
                        ? { color, backgroundColor: `${color}1f` }
                        : undefined
                    }
                  >
                    {block.speaker}
                  </div>
                ) : null}
                <div className="transcript-block-text">{block.text}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
