# tools/file_tools.py
import os
from tools.core import agent_tool
from database.connection import APP_DIR

WORKSPACE_DIR = os.path.join(APP_DIR, "workspace")

def _get_safe_path(filename: str) -> str:
    """Ensures file path cannot escape the sandboxed workspace directory."""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    safe_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filename))
    if not safe_path.startswith(WORKSPACE_DIR):
        raise ValueError("Permission denied: Cannot access files outside the workspace directory.")
    return safe_path

@agent_tool()
def write_file(filename: str, content: str) -> str:
    """Writes text content to a specified file inside the workspace storage."""
    try:
        target_path = _get_safe_path(filename)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to '{filename}'."
    except Exception as e:
        return f"Error writing file '{filename}': {e}"

@agent_tool()
def read_file(filename: str) -> str:
    """Reads and returns text content from a specified file inside workspace storage."""
    try:
        target_path = _get_safe_path(filename)
        if not os.path.exists(target_path):
            return f"Error: File '{filename}' does not exist."
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{filename}': {e}"

# tools/pdf_tools.py
import io
import logging
import markdown
from xhtml2pdf import pisa

from tools.core import agent_tool
from utils.telegram_helpers import send_telegram_document

logger = logging.getLogger("tools.pdf_tools")

@agent_tool()
def generate_pdf(
    markdown_content: str,
    filename: str = "report.pdf",
    conversation_id: int = None
) -> str:
    """Converts markdown into a formatted PDF in RAM and sends it directly to Telegram."""
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    markdown_content = (
        markdown_content.replace("—", "-").replace("–", "-")
        .replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'").replace("…", "...")
    )

    try:
        html_body = markdown.markdown(markdown_content, extensions=["tables", "fenced_code"])
        full_html = f"""
        <html>
        <head>
            <style>
                @page {{ margin: 2cm; }}
                body {{ font-family: Helvetica, Arial, sans-serif; font-size: 12pt; line-height: 1.6; color: #333333; }}
                table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                th {{ background-color: #f2f2f2; font-weight: bold; text-align: left; border: 1px solid #dddddd; padding: 8px; }}
                td {{ border: 1px solid #dddddd; padding: 8px; }}
                code {{ background-color: #f4f4f4; padding: 2px 4px; font-family: Courier, monospace; font-size: 10pt; }}
                pre {{ background-color: #f4f4f4; padding: 10px; border: 1px solid #dddddd; }}
            </style>
        </head>
        <body>{html_body}</body>
        </html>
        """

        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(full_html, dest=pdf_buffer)

        if pisa_status.err:
            return "Error: PDF generation failed due to formatting errors."

        pdf_buffer.seek(0)

        # Deliver via generic helper!
        sent = send_telegram_document(
            conversation_id=conversation_id,
            document_obj=pdf_buffer,
            filename=filename,
            caption=f"📄 *Generated PDF:* `{filename}`"
        )

        if sent:
            return f"Success: PDF '{filename}' generated and sent directly to your Telegram chat!"
        return f"Error: PDF generated, but failed to deliver via Telegram."

    except Exception as e:
        logger.exception(f"PDF generation error: {e}")
        return f"Error: Failed to generate PDF: {e}"