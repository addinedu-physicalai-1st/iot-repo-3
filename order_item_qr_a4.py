#!/usr/bin/env python3
"""
order_items 전건을 2cm x 2cm QR 코드로 A4 PDF 생성.

- DB에서 order_items 전체 조회 (order_item_id, order_id, item_code).
- 각 행마다 QR 1개 (payload: item_code 또는 order_item_id + item_code).
- QR 크기 2cm x 2cm, A4 용지에 격자 배치.

실행: uv run python order_item_qr_a4.py [-o 출력경로]
DB: MYSQL_* 또는 SOY_DATABASE_URL (soy-server와 동일).
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import text
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# QR 한 변 = 2cm / QR 위 order_id·품명 텍스트용 여유
QR_SIZE_MM = 20
QR_SIZE = QR_SIZE_MM * mm
LABEL_HEIGHT_MM = 8  # order_id + 품명 두 줄
CELL_HEIGHT = QR_SIZE + LABEL_HEIGHT_MM * mm

# A4 (210 x 297 mm), 여백
PAGE_WIDTH_MM, PAGE_HEIGHT_MM = 210, 297
MARGIN_MM = 15
FONT_SIZE_ORDER = 8
FONT_SIZE_NAME = 6  # 품명 작게
MAX_NAME_CHARS = 14  # 셀 폭에 맞게 품명 잘라냄

# 한글 폰트 (inbound_invoice_pdf.py와 동일)
_FONT_KOREAN = "Korean"
_KOREAN_FONT_PATHS = [
    Path(__file__).resolve().parent / "fonts" / "NanumGothic.ttf",
    Path(__file__).resolve().parent / "fonts" / "Malgun.ttf",
    Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"),
    Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    Path("/Library/Fonts/Apple SD Gothic Neo.ttf"),
    Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts" / "malgun.ttf",
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
]
_korean_font_registered = False


def _register_korean_font() -> None:
    """한글 TTF 등록 (한 번만)."""
    global _korean_font_registered
    if _korean_font_registered:
        return
    for path in _KOREAN_FONT_PATHS:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(_FONT_KOREAN, str(path)))
                _korean_font_registered = True
                return
            except Exception:
                continue
    raise FileNotFoundError(
        "한글 폰트를 찾을 수 없습니다. 프로젝트 루트 fonts/ 에 NanumGothic.ttf 등을 넣어주세요."
    )


def _get_engine() -> Engine:
    url = os.environ.get("SOY_DATABASE_URL")
    if not url:
        user = os.environ.get("MYSQL_USER", "soy")
        password = os.environ.get("MYSQL_PASSWORD", "soy")
        host = os.environ.get("MYSQL_HOST", "127.0.0.1")
        port = os.environ.get("MYSQL_PORT", "3333")
        database = os.environ.get("MYSQL_DATABASE", "soydb")
        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)


def load_order_items(engine: Engine) -> list[tuple[int, int, str, str]]:
    """(order_item_id, order_id, item_code, product_name) 리스트, order_item_id 순."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT oi.order_item_id, oi.order_id, oi.item_code, p.name
                FROM order_items oi
                INNER JOIN products p ON p.item_code = oi.item_code
                ORDER BY oi.order_item_id
            """)
        ).fetchall()
    return [(r[0], r[1], r[2], (r[3] or "").strip()) for r in rows]


def qr_payload(order_item_id: int, item_code: str) -> str:
    """QR에 넣을 문자열 (스캔 시 식별용). plain text item_code만 반환."""
    return item_code


def make_qr_image(payload: str, size_mm: float = QR_SIZE_MM) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def draw_qr_on_canvas(
    canvas: Canvas,
    qr_buf: io.BytesIO,
    x_pt: float,
    y_pt: float,
    size_pt: float,
) -> None:
    from reportlab.lib.utils import ImageReader
    canvas.drawImage(ImageReader(qr_buf), x_pt, y_pt, width=size_pt, height=size_pt)


def _truncate_name(name: str) -> str:
    """품명이 너무 길면 잘라냄."""
    if len(name) <= MAX_NAME_CHARS:
        return name
    return name[: MAX_NAME_CHARS - 1] + "…"


def build_pdf(out_path: str, items: list[tuple[int, int, str, str]]) -> None:
    """A4에 2cm x 2cm QR 격자. 각 QR 위에 order_id + 품명(작게)."""
    _register_korean_font()
    if not items:
        raise ValueError("order_items가 비어 있습니다.")

    page_w = PAGE_WIDTH_MM * mm
    page_h = PAGE_HEIGHT_MM * mm
    margin = MARGIN_MM * mm
    qr_pt = QR_SIZE

    cols = int((page_w - 2 * margin) // qr_pt)
    rows_per_page = int((page_h - 2 * margin) // CELL_HEIGHT)

    c = Canvas(out_path, pagesize=(page_w, page_h))
    n = len(items)
    i = 0

    while i < n:
        y_start = page_h - margin - CELL_HEIGHT

        for r in range(rows_per_page):
            if i >= n:
                break
            for col in range(cols):
                if i >= n:
                    break
                order_item_id, order_id, item_code, product_name = items[i]
                x_pt = margin + col * qr_pt
                cell_bottom = y_start - r * CELL_HEIGHT - CELL_HEIGHT
                cell_top = cell_bottom + CELL_HEIGHT
                y_qr = cell_bottom
                # 셀 위쪽: 1줄 order_id, 2줄 품명(작게)
                y_order = cell_top - 2 * mm
                y_name = cell_top - 5 * mm

                c.setFont(_FONT_KOREAN, FONT_SIZE_ORDER)
                c.drawString(x_pt, y_order, f"order_id: {order_id}")
                c.setFont(_FONT_KOREAN, FONT_SIZE_NAME)
                c.drawString(x_pt, y_name, _truncate_name(product_name))

                payload = qr_payload(order_item_id, item_code)
                qr_buf = make_qr_image(payload)
                draw_qr_on_canvas(c, qr_buf, x_pt, y_qr, qr_pt)
                i += 1

        if i < n:
            c.showPage()

    c.save()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="order_items → 2cm×2cm QR A4 PDF")
    parser.add_argument("-o", "--output", default="order_item_qr_a4.pdf", help="출력 PDF 경로")
    args = parser.parse_args()

    engine = _get_engine()
    try:
        items = load_order_items(engine)
    except Exception as e:
        print(f"DB 오류: {e}", file=sys.stderr)
        sys.exit(1)

    if not items:
        print("order_items가 없습니다.", file=sys.stderr)
        sys.exit(1)

    out_path = args.output
    build_pdf(out_path, items)
    print(f"생성 완료: {out_path} (총 {len(items)}개 QR)")


if __name__ == "__main__":
    main()
