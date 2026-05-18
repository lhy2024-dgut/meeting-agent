import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter


class PDFEngine:
    """PDF 处理，支持填充模板和插入文本。

    中文渲染使用 PyMuPDF 内置 CJK 字体 (china-s)，
    无需额外安装系统字体。
    """

    def __init__(self):
        pass

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
        doc = fitz.open(template_path)
        for page in doc:
            y = 50
            for key, text in context.items():
                page.insert_text((50, y), f"{key}: {str(text)[:200]}", fontname="china-s", fontsize=12)
                y += 20
        doc.save(output_path)
        doc.close()
        return output_path

    def create_pdf_from_markdown(self, markdown_content, output_path):
        doc = fitz.open()
        page = doc.new_page()
        y = 50
        for line in (markdown_content or "").split("\n"):
            page.insert_text((50, y), line[:200], fontname="china-s", fontsize=12)
            y += 20
        doc.save(output_path)
        return output_path
