from chains.minutes_chain import MinutesChain, PLACEHOLDER_NO_ACTION, PLACEHOLDER_NO_RESOLUTION
from chains.export_chain import ExportChain
from engines.asr_engine import ASREngine, _build_initial_prompt
from logger import get_logger
from rag.retriever import get_retriever

logger = get_logger(__name__)

_FALLBACK_TRANSCRIPT_LEN = 4000


class MeetingService:
    """会议处理完整流程，所有依赖通过构造函数注入"""

    def __init__(self, db_repo, asr_engine=None, minutes_chain=None, export_chain=None):
        self.db = db_repo
        self._asr = asr_engine
        self.minutes_chain = minutes_chain or MinutesChain()
        self.export_chain = export_chain or ExportChain()

    @property
    def asr(self):
        if self._asr is None:
            self._asr = ASREngine()
        return self._asr

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
        terms=None,
        progress_callback=None,
    ):
        """批量处理：ASR → 分类 → LLM → 持久化 → RAG → 导出"""
        cached = self.db.get_meeting_by_hash(file_hash)
        if not terms and cached and any(
            [cached.minutes_text, cached.action_items_text, cached.resolutions_text]
        ):
            return self._handle_cache_hit(cached, output_format, template_path, progress_callback)

        if progress_callback:
            progress_callback(10, "🎤 语音识别中...")
        initial_prompt = _build_initial_prompt(terms) if terms else None
        segments, duration = self.asr.transcribe(file_path, initial_prompt=initial_prompt)
        transcript = " ".join(seg.get("text", "") for seg in segments)

        return self._finalize(
            segments, transcript, file_path, file_hash, title, meeting_dt,
            output_format, template_path, progress_callback, terms=terms,
        )

    def process_stream(
        self,
        file_path,
        file_hash,
        title,
        meeting_dt,
        output_format="docx",
        template_path=None,
        terms=None,
        progress_callback=None,
    ):
        """流式处理：边转写边返回结果"""
        progress = {"pct": 0, "msg": "", "segments": [], "transcript_parts": []}

        initial_prompt = _build_initial_prompt(terms) if terms else None
        for item, duration in self.asr.transcribe_iter(file_path, initial_prompt=initial_prompt):
            progress["segments"].append(item)
            progress["transcript_parts"].append(item.get("text", ""))
            progress["pct"] = min(55, int(item["end"] / max(duration, 1) * 55))
            progress["msg"] = f"🎤 实时转写... [{item['end']:.0f}s / {duration:.0f}s]"
            if progress_callback:
                progress_callback(progress["pct"], progress["msg"])
            yield {"type": "segment", "segment": item, "progress": dict(progress)}

        transcript = " ".join(progress["transcript_parts"])
        segments = progress["segments"]

        final = self._finalize(
            segments, transcript, file_path, file_hash, title, meeting_dt,
            output_format, template_path, progress_callback, terms=terms,
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
            "duration_category": cached.duration_category,
            "environment": cached.environment,
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
        terms=None,
    ):
        """Steps 3-7: 分类 → LLM 提取 → 持久化 → RAG 索引 → 导出"""
        # Step 3: 分类（仅基于客观时长，environment 存 "unknown" 等后续 speaker diarization）
        if progress_callback:
            progress_callback(55, "📊 分析会议特征...")
        duration = max((seg.get("end", 0) for seg in segments), default=0)
        duration_category = ASREngine.classify_duration(duration)
        environment = "unknown"
        meeting_id = self.db.create_meeting(
            title, file_path, duration_category, environment, file_hash
        )

        # 保存词表（如果有）
        if terms:
            from services.terms_loader import save_terms
            save_terms(meeting_id, terms)

        # Step 4: LLM 提取
        if progress_callback:
            progress_callback(65, "🤖 生成会议纪要...")
        date_str = meeting_dt.strftime("%Y-%m-%d %H:%M")
        action_items, resolutions, minutes = self.minutes_chain.run(
            transcript, title=title, date=date_str
        )

        if not (minutes or "").strip():
            if len(transcript or "") > _FALLBACK_TRANSCRIPT_LEN:
                logger.warning(
                    "纪要生成返回空，回退原文截断 (%d -> %d 字符)",
                    len(transcript), _FALLBACK_TRANSCRIPT_LEN,
                )
            minutes = (
                f"# 会议纪要：{title}\n\n**日期**：{date_str}\n\n"
                f"## 转录文本\n{(transcript or '无')[:_FALLBACK_TRANSCRIPT_LEN]}"
            )
        if not (action_items or "").strip():
            action_items = PLACEHOLDER_NO_ACTION
        if not (resolutions or "").strip():
            resolutions = PLACEHOLDER_NO_RESOLUTION

        # Step 5: 持久化
        if progress_callback:
            progress_callback(80, "💾 保存结果...")
        self.db.add_transcriptions_bulk(meeting_id, segments)
        self.db.update_meeting_results(meeting_id, minutes, action_items, resolutions)

        # Step 6: 向量索引 (RAG)
        if progress_callback:
            progress_callback(88, "🔍 索引到知识库...")
        try:
            get_retriever().index_meeting(
                meeting_id,
                transcript=transcript,
                minutes=minutes,
                action_items=action_items,
                resolutions=resolutions,
            )
        except Exception as e:
            logger.warning("RAG 索引失败（Embedding 模型不可用）: %s", e)

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
            "duration_category": duration_category,
            "environment": environment,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_speaker_count_heuristic(segments):
        """启发式估计说话人数，仅供 UI 展示参考，不参与数据分类决策"""
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
