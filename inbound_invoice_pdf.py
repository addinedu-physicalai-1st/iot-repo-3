#!/usr/bin/env python3
"""
발주(Order) 송장 PDF 생성기.

- orders 테이블에 있는 발주 전부를 조회하여, 발주별로 PDF 1개 생성.
- QR 코드에는 order_id가 들어 있음.
- 테이블에는 해당 발주의 품목 리스트(물품명, 브랜드, 종류, 용량, 수량) 표시.

실행: uv run python inbound_invoice_pdf.py
DB 설정: MYSQL_* 또는 SOY_DATABASE_URL (soy-server와 동일).
"""
from __future__ import annotations

import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Table, TableStyle
from sqlalchemy import text
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# 한글용 폰트 등록에 쓸 이름
_FONT_KOREAN = "Korean"

# 시도할 한글 지원 TTF/OTC 경로 (OS별)
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
    """한글 지원 TTF를 찾아 등록. 한 번만 호출."""
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
        "한글 폰트를 찾을 수 없습니다. 프로젝트 루트에 fonts/NanumGothic.ttf 를 넣거나 "
        "https://github.com/naver/nanumsquare/ 등에서 TTF를 받아 fonts/ 에 두세요."
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


@dataclass
class OrderItemRow:
    """발주 상세 한 줄 (order_items + products)."""
    item_code: str
    name: str
    brand: str
    category: str | None
    capacity: str | None
    expected_qty: int


@dataclass
class OrderRow:
    """발주 한 건 (order + items)."""
    order_id: int
    order_date: str  # formatted
    status: str
    items: list[OrderItemRow]


def load_orders(engine: Engine) -> list[OrderRow]:
    """orders 전부와 order_items, products JOIN하여 반환."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    o.order_id,
                    o.order_date,
                    o.status,
                    p.item_code,
                    p.name,
                    p.brand,
                    p.category,
                    p.capacity,
                    oi.expected_qty
                FROM orders o
                INNER JOIN order_items oi ON oi.order_id = o.order_id
                INNER JOIN products p ON p.item_code = oi.item_code
                ORDER BY o.order_id, oi.order_item_id
            """)
        ).fetchall()
        order_meta = conn.execute(
            text("SELECT order_id, order_date, status FROM orders ORDER BY order_id")
        ).fetchall()

    # order_id별 품목 행 묶기
    by_order: dict[int, list[tuple]] = {}
    for r in rows:
        oid = r[0]
        if oid not in by_order:
            by_order[oid] = []
        by_order[oid].append(r)

    result: list[OrderRow] = []
    for oid, odate, status in order_meta:
        item_rows = by_order.get(oid, [])
        items = [
            OrderItemRow(
                item_code=r[3],
                name=r[4] or "",
                brand=r[5] or "",
                category=r[6],
                capacity=r[7],
                expected_qty=int(r[8]),
            )
            for r in item_rows
        ]
        date_str = str(odate) if odate else ""
        if hasattr(odate, "strftime"):
            date_str = odate.strftime("%Y-%m-%d %H:%M")
        result.append(
            OrderRow(order_id=oid, order_date=date_str, status=status, items=items)
        )
    return result


def build_qr_payload(order_id: int) -> str:
    """QR에 넣을 JSON 문자열 (order_id)."""
    return json.dumps({"order_id": order_id}, ensure_ascii=False)


def make_qr_image(payload: str, size_mm: float = 35) -> io.BytesIO:
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


def create_order_invoice_pdf(out_path: str, order: OrderRow) -> None:
    """발주 1건에 대한 송장 PDF 생성. QR=order_id, 테이블=품목 리스트."""
    _register_korean_font()

    if not order.items:
        raise ValueError(f"발주 ID {order.order_id}에 품목이 없습니다.")

    payload = build_qr_payload(order.order_id)
    qr_buf = make_qr_image(payload)

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontName = _FONT_KOREAN
    styles["Normal"].fontName = _FONT_KOREAN
    story = []

    # 제목: 발주 송장 — 발주 ID: N, 발주일: ...
    title = Paragraph(
        f"<b>발주 송장</b> — 발주 ID: {order.order_id} &nbsp; 발주일: {order.order_date} &nbsp; 상태: {order.status}",
        styles["Title"],
    )
    story.append(title)
    story.append(Paragraph("<br/>", styles["Normal"]))

    # QR (order_id)
    qr_img = Image(qr_buf, width=35 * mm, height=35 * mm)
    story.append(qr_img)
    story.append(Paragraph("<br/>", styles["Normal"]))

    # 테이블: 물품명, 브랜드, 종류, 용량, 수량
    table_data = [["물품명", "브랜드", "종류", "용량", "수량"]]
    for it in order.items:
        table_data.append(
            [
                it.name,
                it.brand,
                it.category or "-",
                it.capacity or "-",
                str(it.expected_qty),
            ]
        )

    col_widths = [60 * mm, 35 * mm, 35 * mm, 20 * mm, 25 * mm]
    t = Table(table_data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, -1), _FONT_KOREAN),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 10),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#D9E2F3")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#E8EDF7")],
                ),
            ]
        )
    )
    story.append(t)
    doc.build(story)


def main() -> None:
    parser = __import__("argparse").ArgumentParser(description="발주 송장 PDF 생성기 (orders 전건)")
    parser.add_argument(
        "-o", "--out-dir",
        default=".",
        help="PDF 저장 디렉터리 (기본: 현재 디렉터리)",
    )
    args = parser.parse_args()

    print("발주 송장 PDF 생성기 (orders 테이블 전건)")
    print("=" * 50)

    engine = _get_engine()
    try:
        orders = load_orders(engine)
    except Exception as e:
        print(f"DB 연결/조회 실패: {e}")
        print("MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE 또는 SOY_DATABASE_URL 확인.")
        sys.exit(1)

    if not orders:
        print("등록된 발주가 없습니다.")
        sys.exit(0)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    for order in orders:
        out_path = str(out_dir / f"order_invoice_{order.order_id}.pdf")
        try:
            create_order_invoice_pdf(out_path, order)
            created.append(out_path)
            print(f"  생성: order_invoice_{order.order_id}.pdf (품목 {len(order.items)}건)")
        except ValueError as e:
            print(f"  건너뜀 발주 ID {order.order_id}: {e}")
        except Exception as e:
            print(f"  실패 발주 ID {order.order_id}: {e}")

    if created:
        print(f"\n총 {len(created)}개 PDF 생성 완료: {args.out_dir}")
    else:
        print("\n생성된 PDF가 없습니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
