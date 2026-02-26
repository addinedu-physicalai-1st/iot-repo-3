#!/usr/bin/env python3
"""
인바운드 송장 PDF 생성기.

- products 목록을 보여주고, 송장 ID와 물품별 개수를 입력받음.
- QR 코드(NDJSON: 송장 ID + products 배열)와 테이블(물품명, 브랜드, 개수)이 있는 PDF 생성.

실행: uv run python inbound_invoice_pdf.py
DB 설정: MYSQL_* 또는 SOY_DATABASE_URL (soy-server와 동일). 서버 미기동 시에도 DB만 접근 가능하면 됨.
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
class ProductRow:
    product_id: int
    product_name: str
    brand: str


def load_products(engine: Engine) -> list[ProductRow]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT product_id, product_name, brand FROM products ORDER BY product_id"
            )
        ).fetchall()
    return [
        ProductRow(product_id=r[0], product_name=r[1], brand=r[2]) for r in rows
    ]


def input_quantity(prompt: str, default: int = 0) -> int:
    while True:
        s = input(prompt).strip()
        if s == "":
            return default
        try:
            n = int(s)
            if n < 0:
                print("  0 이상의 숫자를 입력하세요.")
                continue
            return n
        except ValueError:
            print("  숫자를 입력하세요.")


def build_ndjson_line(inbound_id: str, products: list[dict]) -> str:
    """QR에 넣을 NDJSON 한 줄 (한 개의 JSON 객체)."""
    payload = {"inbound_id": inbound_id, "products": products}
    return json.dumps(payload, ensure_ascii=False)


def make_qr_image(ndjson_line: str, size_mm: float = 35) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(ndjson_line)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_invoice_products(
    products: list[ProductRow], quantities: list[int]
) -> list[dict]:
    """개수가 0보다 큰 항목만 {'product_name','brand','quantity'} 리스트로."""
    out = []
    for p, q in zip(products, quantities):
        if q <= 0:
            continue
        out.append(
            {
                "product_name": p.product_name,
                "brand": p.brand,
                "quantity": q,
            }
        )
    return out


def create_pdf(
    out_path: str,
    inbound_id: str,
    products: list[ProductRow],
    quantities: list[int],
) -> None:
    _register_korean_font()

    invoice_products = build_invoice_products(products, quantities)
    if not invoice_products:
        raise ValueError("개수를 1개 이상 입력한 물품이 없습니다.")

    ndjson_line = build_ndjson_line(inbound_id, invoice_products)
    qr_buf = make_qr_image(ndjson_line)

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

    # 제목
    title = Paragraph(
        f"<b>인바운드 송장</b> — 송장 ID: {inbound_id}",
        styles["Title"],
    )
    story.append(title)
    story.append(Paragraph("<br/>", styles["Normal"]))

    # QR 코드
    qr_img = Image(qr_buf, width=35 * mm, height=35 * mm)
    story.append(qr_img)
    story.append(Paragraph("<br/>", styles["Normal"]))

    # 테이블: 물품명, 브랜드, 개수
    table_data = [["물품명", "브랜드", "개수"]]
    for p, q in zip(products, quantities):
        if q <= 0:
            continue
        table_data.append([p.product_name, p.brand, str(q)])

    t = Table(table_data, colWidths=[80 * mm, 50 * mm, 25 * mm])
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
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#E8EDF7")]),
            ]
        )
    )
    story.append(t)
    doc.build(story)


# DB 없이 PDF 생성 테스트용 시드 데이터 (migration 003과 동일)
_DEMO_PRODUCTS = [
    ProductRow(1, "국간장", "샘표"),
    ProductRow(2, "국간장", "청정원"),
    ProductRow(3, "국간장", "몽고"),
    ProductRow(4, "진간장", "샘표"),
    ProductRow(5, "진간장", "청정원"),
    ProductRow(6, "진간장", "몽고"),
    ProductRow(7, "양조간장", "샘표"),
    ProductRow(8, "양조간장", "청정원"),
    ProductRow(9, "양조간장", "몽고"),
    ProductRow(10, "맛간장", "샘표"),
    ProductRow(11, "맛간장", "청정원"),
    ProductRow(12, "맛간장", "몽고"),
    ProductRow(13, "어묵간장", "샘표"),
    ProductRow(14, "어묵간장", "청정원"),
    ProductRow(15, "어묵간장", "몽고"),
    ProductRow(16, "Soy sauce", "샘표"),
    ProductRow(17, "Soy sauce", "청정원"),
    ProductRow(18, "Soy sauce", "몽고"),
    ProductRow(19, "Dark soy sauce", "샘표"),
    ProductRow(20, "Dark soy sauce", "청정원"),
    ProductRow(21, "Dark soy sauce", "몽고"),
    ProductRow(22, "Flavored soy sauce", "샘표"),
    ProductRow(23, "Flavored soy sauce", "청정원"),
    ProductRow(24, "Flavored soy sauce", "몽고"),
]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="인바운드 송장 PDF 생성기")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="DB 없이 시드 데이터로 테스트 (물품 목록 일부만 표시)",
    )
    args = parser.parse_args()

    print("인바운드 송장 PDF 생성기")
    print("=" * 50)

    if args.demo:
        products = _DEMO_PRODUCTS[:9]  # 일부만 표시
        print("(데모 모드: DB 없이 시드 물품 사용)\n")
    else:
        engine = _get_engine()
        try:
            products = load_products(engine)
        except Exception as e:
            print(f"DB 연결/조회 실패: {e}")
            print("MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE 또는 SOY_DATABASE_URL 확인.")
            sys.exit(1)

    if not products:
        print("등록된 물품이 없습니다.")
        sys.exit(1)

    print("\n[물품 목록]")
    for i, p in enumerate(products, 1):
        print(f"  {i:2}. {p.product_name} / {p.brand}")

    inbound_id = input("\n송장 ID를 입력하세요: ").strip()
    if not inbound_id:
        print("송장 ID가 비어 있습니다. 종료합니다.")
        sys.exit(1)

    print("\n각 물품의 개수를 입력하세요 (Enter 시 0).")
    quantities: list[int] = []
    for i, p in enumerate(products, 1):
        q = input_quantity(f"  {p.product_name} ({p.brand}): ", default=0)
        quantities.append(q)

    out_path = f"inbound_invoice_{inbound_id}.pdf"
    try:
        create_pdf(out_path, inbound_id, products, quantities)
    except ValueError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print(f"PDF 생성 실패: {e}")
        raise

    print(f"\n생성 완료: {out_path}")


if __name__ == "__main__":
    main()
