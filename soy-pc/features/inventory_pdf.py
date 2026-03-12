"""재고 리포트 PDF 출력."""
import os
import tempfile
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_KOREAN = "Korean"
# inbound_invoice_pdf와 동일한 한글 폰트 경로
_ROOT = Path(__file__).resolve().parent.parent.parent
_KOREAN_FONT_PATHS = [
    _ROOT / "fonts" / "NanumGothic.ttf",
    _ROOT / "fonts" / "Malgun.ttf",
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts" / "malgun.ttf",
]

_korean_font_registered = False


def _register_korean_font() -> None:
    """한글 폰트 등록. 실패 시 예외."""
    global _korean_font_registered
    if _korean_font_registered:
        return
    for path in _KOREAN_FONT_PATHS:
        if path.exists():
            for kwargs in [{}, {"subfontIndex": 0}]:  # TTC는 subfontIndex 필요할 수 있음
                try:
                    pdfmetrics.registerFont(TTFont(_FONT_KOREAN, str(path), **kwargs))
                    _korean_font_registered = True
                    return
                except Exception:
                    continue
    raise FileNotFoundError(
        "한글 폰트를 찾을 수 없습니다. fonts/NanumGothic.ttf 를 넣거나 "
        "fonts-noto-cjk 패키지를 설치하세요."
    )


def export_inventory_pdf(
    data: list[tuple[str, int]],
    chart_image_path: str | None,
    output_path: str,
) -> None:
    """재고 리포트 PDF 저장. data = [(inventory_name, current_qty), ...]"""
    _register_korean_font()
    font_name = _FONT_KOREAN

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    # 제목
    title_style = styles["Title"]
    title_style.fontName = font_name
    story.append(Paragraph("창고별 재고 비율", title_style))
    story.append(Spacer(1, 6 * mm))

    # 출력 일시
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normal_style = styles["Normal"]
    normal_style.fontName = font_name
    story.append(Paragraph(f"출력 일시: {now}", normal_style))
    story.append(Spacer(1, 8 * mm))

    # 차트 이미지
    if chart_image_path and os.path.exists(chart_image_path):
        img = Image(chart_image_path, width=120 * mm, height=120 * mm)
        story.append(img)
        story.append(Spacer(1, 8 * mm))

    # 테이블
    total = sum(v for _, v in data) or 1
    table_data = [["창고", "수량", "비율(%)"]]
    for name, qty in data:
        pct = 100 * qty / total if total > 0 else 0
        table_data.append([name, str(qty), f"{pct:.1f}"])

    table = Table(table_data, colWidths=[50 * mm, 40 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8dcc4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1c1c1c")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(table)

    doc.build(story)
