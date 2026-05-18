from chains.minutes_chain import MinutesChain
from chains.export_chain import ExportChain
from engines.asr_engine import ASREngine


class MeetingService:
    """会议处理完整流程"""

    _retriever = None

    def __init__(self, db_repo):
        self.db = db_repo
        self._asr = None
        self.minutes_chain = MinutesChain()
        self.export_chain = ExportChain()

    @property
    def asr(self):
        """延迟加载 ASR 引擎，避免导出等操作浪费 Whisper 模型内存"""
        if self._asr is None:
            self._asr = ASREngine()
        return self._asr

    @classmethod
    def _get_retriever(cls):
        if cls._retriever is None:
            from rag.retriever import get_retriever

            cls._retriever = get_retriever()
        return cls._retriever

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        progress_callback=None,
    ):
        """批量处理：ASR → 分类 → LLM → 持久化 → RAG → 导出"""
        # Step 1: 查缓存
        cached = self.db.get_meeting_by_hash(file_hash)
        if cached and any(
            [cached.minutes_text, cached.action_items_text, cached.resolutions_text]
        ):
            return self._handle_cache_hit(cached, output_format, template_path, progress_callback)

        # Step 2: ASR
        if progress_callback:
            progress_callback(10, "🎤 语音识别中...")
        segments, duration = self.asr.transcribe(file_path)
        transcript = " ".join(seg.get("text", "") for seg in segments)

        # Steps 3-7: 共享流水线
        return self._finalize(
            segments, transcript, file_path, file_hash, title, meeting_dt,
            output_format, template_path, progress_callback,
        )

    def process_stream(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        progress_callback=None,
    ):
        """流式处理：边转写边返回结果，适合长会议和实时展示"""
        progress = {"pct": 0, "msg": "", "segments": [], "transcript_parts": []}

        # ASR 增量转写
        for item, duration in self.asr.transcribe_iter(file_path):
            progress["segments"].append(item)
            progress["transcript_parts"].append(item.get("text", ""))
            progress["pct"] = min(55, int(item["end"] / max(duration, 1) * 55))
            progress["msg"] = f"🎤 实时转写... [{item['end']:.0f}s / {duration:.0f}s]"
            if progress_callback:
                progress_callback(progress["pct"], progress["msg"])
            yield {"type": "segment", "segment": item, "progress": dict(progress)}

        transcript = " ".join(progress["transcript_parts"])
        segments = progress["segments"]

        # Steps 3-7: 共享流水线
        final = self._finalize(
            segments, transcript, file_path, file_hash, title, meeting_dt,
            output_format, template_path, progress_callback,
        )
        yield {"type": "complete", "data": final}

        if progress_callback:
            progress_callback(100, "OK 完成")

    def export(self, data, output_format="docx", template_path=None):
        return self.export_chain.run(data, output_format, template_path)

    # ------------------------------------------------------------------
    # Private: shared pipeline
    # ------------------------------------------------------------------

    def _handle_cache_hit(self, cached, output_format, template_path, progress_callback):
        segments = [
            {
                "start": t.start_time,
                "end": t.end_time,
                "text": t.text,
                "duration": (t.end_time or 0) - (t.start_time or 0),
            }
            for t in cached.transcriptions
        ]
        transcript = " ".join(seg["text"] for seg in segments)
        output_data = {
            "meeting_id": cached.id,
            "title": cached.title,
            "date": cached.created_at.strftime("%Y-%m-%d %H:%M"),
            "minutes": cached.minutes_text or "",
            "action_items": cached.action_items_text or "",
            "resolutions": cached.resolutions_text or "",
        }
        output_path = self.export_chain.run(output_data, output_format, template_path)
        if progress_callback:
            progress_callback(100, "⚡ 缓存命中")
        return {
            "transcript": transcript,
            "segments": segments,
            "minutes": cached.minutes_text or "",
            "action_items": cached.action_items_text or "",
            "resolutions": cached.resolutions_text or "",
            "meeting_id": cached.id,
            "title": cached.title,
            "output_path": output_path,
        }

    def _finalize(
        self,
        segments,
        transcript,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        progress_callback=None,
    ):
        """Steps 3-7: 分类 → LLM 提取 → 持久化 → RAG 索引 → 导出。

        process() 和 process_stream() 共享此方法，避免重复代码。
        """
        # Step 3: 分类
        if progress_callback:
            progress_callback(55, "📊 分析会议特征...")
        speakers = self._estimate_speaker_count_heuristic(segments)
        duration = max((seg.get("end", 0) for seg in segments), default=0)
        duration_category, environment = ASREngine.classify_meeting_type(
            duration, speakers, 0.3
        )
        meeting_id = self.db.create_meeting(
            title, file_path, duration_category, environment, file_hash
        )

        # Step 4: LLM 提取
        if progress_callback:
            progress_callback(65, "🤖 生成会议纪要...")
        date_str = meeting_dt.strftime("%Y-%m-%d %H:%M")
        action_items, resolutions, minutes = self.minutes_chain.run(
            transcript, title=title, date=date_str
        )

        # 兜底
        if not (minutes or "").strip():
            minutes = (
                f"# 会议纪要：{title}\n\n**日期**：{date_str}\n\n"
                f"## 转录文本\n{(transcript or '无')[:4000]}"
            )
        if not (action_items or "").strip():
            action_items = "本次会议未明确待办事项。"
        if not (resolutions or "").strip():
            resolutions = "本次会议未明确决议。"

        # Step 5: 持久化
        if progress_callback:
            progress_callback(80, "💾 保存结果...")
        self.db.add_transcriptions_bulk(meeting_id, segments)
        self.db.update_meeting_results(meeting_id, minutes, action_items, resolutions)

        # Step 6: 向量索引 (RAG)
        if progress_callback:
            progress_callback(88, "🔍 索引到知识库...")
        try:
            self._get_retriever().index_meeting(
                meeting_id,
                transcript=transcript,
                minutes=minutes,
                action_items=action_items,
                resolutions=resolutions,
            )
        except Exception as e:
            print(f"[WARN] RAG 索引失败（Embedding 模型不可用）: {e}")

        # Step 7: 导出
        if progress_callback:
            progress_callback(95, "📄 导出文档...")
        output_data = {
            "meeting_id": meeting_id,
            "title": title,
            "date": date_str,
            "minutes": minutes,
            "action_items": action_items,
            "resolutions": resolutions,
        }
        output_path = self.export_chain.run(output_data, output_format, template_path)

        if progress_callback:
            progress_callback(100, "OK 完成")

        return {
            "transcript": transcript,
            "segments": segments,
            "minutes": minutes,
            "action_items": action_items,
            "resolutions": resolutions,
            "meeting_id": meeting_id,
            "title": title,
            "output_path": output_path,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_speaker_count_heuristic(segments):
        """基于片段平均时长粗略估计说话人数。

        注意：这是启发式估计，不是真正的说话人分离 (diarization)。
        假设更短的平均片段 = 更多说话人交替。返回值 1-4。
        """
        if not segments:
            return 1
        avg = sum(seg.get("duration", 0.0) for seg in segments) / max(len(segments), 1)
        if avg < 3:
            return 4
        if avg < 5:
            return 3
        if avg < 15:
            return 2
        return 1
