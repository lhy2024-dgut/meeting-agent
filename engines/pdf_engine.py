"""PDF 处理，支持从 Markdown 创建 PDF（自动换行 + 中文排版）"""

import fitz  # PyMuPDF
from pathlib import Path
from pypdf import PdfReader, PdfWriter

from logger import get_logger

logger = get_logger(__name__)

# ── 系统字体扫描 ──────────────────────────────────────────────
_CJK_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
    "C:/Windows/Fonts/simsun.ttc",      # 宋体
    "C:/Windows/Fonts/NotoSansSC-VF.ttf",
    "C:/Windows/Fonts/NotoSerifSC-VF.ttf",
    "C:/Windows/Fonts/STFANGSO.TTF",    # 仿宋
    "C:/Windows/Fonts/STKAITI.TTF",     # 楷体
]
_FONT_CACHE = {}


def _get_cjk_font():
    """获取一个 fitz.Font 对象（缓存），内置 CJK 字体优先"""
    global _FONT_CACHE
    if "cjk" in _FONT_CACHE:
        return _FONT_CACHE["cjk"]
    try:
        font = fitz.Font("china-s")
        _FONT_CACHE["cjk"] = font
        logger.info(f"PDF 使用内置字体: {font.name}")
        return font
    except Exception as e:
        logger.warning(f"内置 CJK 字体加载失败 ({e})，尝试系统字体…")
        for fp in _CJK_FONTS:
            if Path(fp).exists():
                try:
                    font = fitz.Font(fontfile=fp)
                    _FONT_CACHE["cjk"] = font
                    logger.info(f"PDF 使用系统字体: {fp}")
                    return font
                except Exception:
                    continue
        logger.error("没有可用中文字体，PDF 中文可能显示为 tofu")
        _FONT_CACHE["cjk"] = None
        return None


# ── 排版常量 ──────────────────────────────────────────────────
A4_W, A4_H = 595, 842
MARGIN = 50
BODY_W = A4_W - MARGIN * 2  # = 495
LINE_SPACING = 1.5  # 行距倍数
PARAGRAPH_GAP = 6    # 段间距


class PDFEngine:
    """PDF 处理，支持从 Markdown 创建排版良好的 PDF。

    全部使用手动换行（基于 font.text_length 度量），
    完全避开 PyMuPDF insert_textbox 的返回值偏移 bug，
    同时提供更精确的排版控制。
    """

    def __init__(self):
        self._cjk_font = _get_cjk_font()
        # fontname 用 "china-s"（PyMuPDF 内置 CJK 字体短名）
        # 字体对象 self._cjk_font 仅用于 text_length() 度量
        self._cjk_font_name = "china-s"

    # ── 工具方法 ──────────────────────────────────────────────

    def _line_height(self, fontsize: float) -> float:
        """返回一行文本占用的基线到基线距离"""
        return fontsize * LINE_SPACING

    def _measure(self, text: str, fontsize: float) -> float:
        """测量文本像素宽度"""
        if self._cjk_font:
            return self._cjk_font.text_length(text, fontsize=fontsize)
        # fallback: 粗略估算
        cjk_count = sum(1 for c in text if '一' <= c <= '鿿')
        ascii_count = len(text) - cjk_count
        return (cjk_count * fontsize + ascii_count * fontsize * 0.55)

    def _wrap_text(self, text: str, fontsize: float, max_width: float, indent: float = 0) -> list[str]:
        """将文本按宽度拆分为多行，返回行列表"""
        effective_width = max_width - indent
        if effective_width <= 0:
            return [text]

        lines = []
        current = ""
        for char in text:
            test = current + char
            if self._measure(test, fontsize) > effective_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
        return lines if lines else [text]

    def _render_text(self, page, text: str, fontsize: float, color, indent: float, y: float) -> float:
        """在 page 上渲染文本（自动换行），返回下一行基线 y"""
        lines = self._wrap_text(text, fontsize, BODY_W, indent)
        lh = self._line_height(fontsize)
        for line in lines:
            page.insert_text(
                (MARGIN + indent, y), line,
                fontsize=fontsize, fontname=self._cjk_font_name,
                color=color,
            )
            y += lh
        return y

    # ── 从 Markdown 创建 PDF ────────────────────────────────

    def create_pdf_from_markdown(self, markdown_content: str, output_path: str) -> str:
        """从 Markdown 内容创建 PDF（自动换行 + 中文支持 + 标题/列表样式）"""
        doc = fitz.open()
        page = doc.new_page(width=A4_W, height=A4_H)
        y = MARGIN

        for line in (markdown_content or "").split("\n"):
            # ── 翻页检查 ──
            if y > A4_H - MARGIN - self._line_height(18) * 2:
                page = doc.new_page(width=A4_W, height=A4_H)
                y = MARGIN

            stripped = line.strip()

            # ── 空行 → 段间距 ──
            if not stripped:
                y += self._line_height(11) * 0.6
                continue

            # ── 标题 (H1) ──
            if stripped.startswith("# "):
                y = self._render_text(page, stripped[2:], 18, (0.1, 0.1, 0.18), 0, y)
                y += PARAGRAPH_GAP

            # ── 标题 (H2) ──
            elif stripped.startswith("## "):
                y = self._render_text(page, stripped[3:], 15, (0.18, 0.23, 0.37), 0, y)
                y += PARAGRAPH_GAP

            # ── 列表项 ──
            elif stripped.startswith("- "):
                y = self._render_text(page, "• " + stripped[2:], 11, (0, 0, 0), 10, y)
                y += 2

            # ── 普通段落 ──
            else:
                y = self._render_text(page, line, 11, (0, 0, 0), 0, y)

        doc.save(output_path)
        doc.close()
        logger.info(f"PDF 已生成: {output_path}")
        return str(output_path)

    # ── PDF 模板填充（备用） ─────────────────────────────────

    def fill_template_with_context(self, template_path, context, output_path):
        reader = PdfReader(template_path)
        fields = reader.get_fields()
        if fields:
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.update_page_form_field_values(writer.pages[0], context)
            with open(output_path, "wb") as f:
                writer.write(f)
            return output_path
        return self.overlay_text_on_pdf(template_path, context, output_path)

    def overlay_text_on_pdf(self, template_path, context, output_path):
        """在 PDF 模板上叠加文本（使用 fitz，修复了返回值偏移 bug）"""
        doc = fitz.open(template_path)
        for page in doc:
            y = MARGIN
            for key, text in context.items():
                content = str(text)
                if not content.strip():
                    continue
                # 估算剩余空间
                if A4_H - MARGIN - y < self._line_height(11):
                    continue
                y = self._render_text(page, content, 11, None, 0, y)
                y += 4
        doc.save(output_path)
        doc.close()
        return output_path

    # ── 辅助 ──────────────────────────────────────────────────

    def list_system_fonts(self):
        """列出系统中文字体路径"""
        return [fp for fp in _CJK_FONTS if Path(fp).exists()]
