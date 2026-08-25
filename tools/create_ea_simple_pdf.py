"""Create the six-page plain-English StraddleReplica EA guide."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)

NAVY = HexColor("#102A43")
NAVY_2 = HexColor("#173F5F")
GOLD = HexColor("#C89B3C")
GOLD_LIGHT = HexColor("#F7F0DF")
BLUE = HexColor("#2E6F9E")
BLUE_LIGHT = HexColor("#EAF2F8")
RED = HexColor("#B54B4B")
RED_LIGHT = HexColor("#FBEDEE")
GREEN = HexColor("#2F7D65")
GREEN_LIGHT = HexColor("#EAF5F1")
TEXT = HexColor("#263746")
MUTED = HexColor("#647484")
LIGHT = HexColor("#F4F6F8")
BORDER = HexColor("#D9E1E8")
WHITE = HexColor("#FFFFFF")


BODY = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=10,
    leading=14,
    textColor=TEXT,
    alignment=TA_LEFT,
    spaceAfter=0,
)
BODY_SMALL = ParagraphStyle(
    "BodySmall",
    parent=BODY,
    fontSize=8.8,
    leading=12,
)
BODY_TINY = ParagraphStyle(
    "BodyTiny",
    parent=BODY,
    fontSize=7.8,
    leading=10,
)
CARD_TITLE = ParagraphStyle(
    "CardTitle",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=10.5,
    leading=13,
    textColor=NAVY,
)
SECTION = ParagraphStyle(
    "Section",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=12,
    leading=15,
    textColor=NAVY,
)
CENTER_SMALL = ParagraphStyle(
    "CenterSmall",
    parent=BODY_SMALL,
    alignment=TA_CENTER,
)
CENTER_TINY = ParagraphStyle(
    "CenterTiny",
    parent=BODY_TINY,
    alignment=TA_CENTER,
)


def draw_paragraph(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y_top: float,
    width: float,
    style: ParagraphStyle = BODY,
    max_height: float | None = None,
) -> float:
    """Draw wrapped text from a top coordinate and return its bottom y."""
    paragraph = Paragraph(text, style)
    _, height = paragraph.wrap(width, PAGE_HEIGHT)
    if max_height is not None and height > max_height + 0.1:
        raise ValueError(
            f"Paragraph is too tall ({height:.1f} > {max_height:.1f}): {text[:70]}"
        )
    paragraph.drawOn(pdf, x, y_top - height)
    return y_top - height


def draw_header(pdf: canvas.Canvas, page_number: int, title: str) -> None:
    pdf.setFillColor(NAVY)
    pdf.rect(0, PAGE_HEIGHT - 92, PAGE_WIDTH, 92, stroke=0, fill=1)

    pdf.setFillColor(GOLD)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(MARGIN, PAGE_HEIGHT - 26, "STRADDLEREPLICA EA")

    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(MARGIN, PAGE_HEIGHT - 61, title)

    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica", 8)
    page_text = f"{page_number} / 6"
    pdf.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 26, page_text)


def draw_footer(pdf: canvas.Canvas, page_number: int) -> None:
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.7)
    pdf.line(MARGIN, 43, PAGE_WIDTH - MARGIN, 43)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(MARGIN, 27, "Simple operating guide - no profit guarantee")
    pdf.drawRightString(
        PAGE_WIDTH - MARGIN, 27, f"StraddleReplica EA | Page {page_number}"
    )


def draw_section_label(
    pdf: canvas.Canvas, text: str, x: float, y: float, width: float = CONTENT_WIDTH
) -> None:
    pdf.setFillColor(GOLD)
    pdf.roundRect(x, y - 2, 24, 3, 1.5, stroke=0, fill=1)
    draw_paragraph(pdf, text, x + 34, y + 4, width - 34, SECTION, 20)


def draw_card(
    pdf: canvas.Canvas,
    x: float,
    y_top: float,
    width: float,
    height: float,
    title: str,
    body: str,
    *,
    accent: object = GOLD,
    fill: object = WHITE,
    title_style: ParagraphStyle = CARD_TITLE,
    body_style: ParagraphStyle = BODY_SMALL,
) -> None:
    y_bottom = y_top - height
    pdf.setFillColor(fill)
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(0.7)
    pdf.roundRect(x, y_bottom, width, height, 8, stroke=1, fill=1)
    pdf.setFillColor(accent)
    pdf.roundRect(x, y_bottom, 5, height, 2.5, stroke=0, fill=1)

    inner_x = x + 17
    inner_width = width - 31
    current_y = y_top - 16
    current_y = draw_paragraph(
        pdf, title, inner_x, current_y, inner_width, title_style, 30
    )
    body_top = current_y - 7
    available_height = body_top - (y_bottom + 10)
    draw_paragraph(
        pdf,
        body,
        inner_x,
        body_top,
        inner_width,
        body_style,
        available_height,
    )


def draw_metric(
    pdf: canvas.Canvas,
    x: float,
    y_top: float,
    width: float,
    height: float,
    value: str,
    label: str,
) -> None:
    y_bottom = y_top - height
    pdf.setFillColor(LIGHT)
    pdf.setStrokeColor(BORDER)
    pdf.roundRect(x, y_bottom, width, height, 8, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(x + width / 2, y_top - 31, value)
    draw_paragraph(
        pdf,
        label,
        x + 12,
        y_top - 45,
        width - 24,
        CENTER_SMALL,
        height - 49,
    )


def draw_bullets(
    pdf: canvas.Canvas,
    items: list[str],
    x: float,
    y_top: float,
    width: float,
    *,
    style: ParagraphStyle = BODY,
    gap: float = 8,
    bullet_color: object = GOLD,
) -> float:
    current_y = y_top
    for item in items:
        pdf.setFillColor(bullet_color)
        pdf.circle(x + 4, current_y - 6, 2.4, stroke=0, fill=1)
        current_y = draw_paragraph(
            pdf, item, x + 15, current_y, width - 15, style
        )
        current_y -= gap
    return current_y


def draw_numbered_steps(
    pdf: canvas.Canvas,
    steps: list[tuple[str, str]],
    x: float,
    y_top: float,
    width: float,
    *,
    number_color: object = NAVY_2,
    style: ParagraphStyle = BODY_SMALL,
    gap: float = 9,
) -> float:
    current_y = y_top
    for index, (title, body) in enumerate(steps, start=1):
        pdf.setFillColor(number_color)
        pdf.circle(x + 12, current_y - 11, 11, stroke=0, fill=1)
        pdf.setFillColor(WHITE)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.drawCentredString(x + 12, current_y - 14, str(index))
        combined = f"<b>{title}</b> {body}"
        bottom = draw_paragraph(
            pdf, combined, x + 32, current_y, width - 32, style
        )
        current_y = min(bottom, current_y - 22) - gap
    return current_y


def draw_arrow(
    pdf: canvas.Canvas,
    x1: float,
    y: float,
    x2: float,
    *,
    color: object = GOLD,
) -> None:
    pdf.setStrokeColor(color)
    pdf.setFillColor(color)
    pdf.setLineWidth(1.5)
    pdf.line(x1, y, x2 - 6, y)
    path = pdf.beginPath()
    path.moveTo(x2, y)
    path.lineTo(x2 - 7, y + 4)
    path.lineTo(x2 - 7, y - 4)
    path.close()
    pdf.drawPath(path, stroke=0, fill=1)


def draw_grid_diagram(
    pdf: canvas.Canvas, x: float, y_top: float, width: float, height: float
) -> None:
    y_bottom = y_top - height
    pdf.setFillColor(LIGHT)
    pdf.setStrokeColor(BORDER)
    pdf.roundRect(x, y_bottom, width, height, 10, stroke=1, fill=1)

    left = x + 58
    right = x + width - 58
    center_y = y_bottom + height / 2
    spacing = 21

    pdf.setFillColor(BLUE_LIGHT)
    pdf.roundRect(
        x + 14,
        center_y + 14,
        width - 28,
        height / 2 - 28,
        7,
        stroke=0,
        fill=1,
    )
    pdf.setFillColor(RED_LIGHT)
    pdf.roundRect(
        x + 14,
        y_bottom + 14,
        width - 28,
        height / 2 - 28,
        7,
        stroke=0,
        fill=1,
    )

    pdf.setFillColor(BLUE)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(x + 26, y_top - 27, "BUY STOP ZONE - 30 LEVELS ABOVE")
    pdf.setFillColor(RED)
    pdf.drawString(x + 26, y_bottom + 21, "SELL STOP ZONE - 30 LEVELS BELOW")

    for level in range(1, 6):
        buy_y = center_y + (level * spacing)
        sell_y = center_y - (level * spacing)

        pdf.setStrokeColor(BLUE)
        pdf.setLineWidth(0.8 if level < 5 else 1.4)
        pdf.line(left, buy_y, right, buy_y)
        pdf.setFillColor(BLUE)
        pdf.circle(right - 7, buy_y, 2.2, stroke=0, fill=1)

        pdf.setStrokeColor(RED)
        pdf.setLineWidth(0.8 if level < 5 else 1.4)
        pdf.line(left, sell_y, right, sell_y)
        pdf.setFillColor(RED)
        pdf.circle(left + 7, sell_y, 2.2, stroke=0, fill=1)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2)
    pdf.line(left - 8, center_y, right + 8, center_y)
    pdf.setFillColor(NAVY)
    pdf.roundRect(
        x + width / 2 - 62,
        center_y - 12,
        124,
        24,
        6,
        stroke=0,
        fill=1,
    )
    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(x + width / 2, center_y - 3, "STARTING PRICE")

    pdf.setFillColor(BLUE)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(right, y_top - 50, "Price rises")
    pdf.setFillColor(RED)
    pdf.drawRightString(right, y_bottom + 40, "Price falls")

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.3)
    pdf.drawRightString(
        right, center_y + 33, "Outer levels use larger lots"
    )
    pdf.drawRightString(
        right, center_y - 42, "Outer levels use larger lots"
    )


def draw_cycle_flow(
    pdf: canvas.Canvas, x: float, y_top: float, width: float
) -> None:
    labels = [
        ("1", "Place grid"),
        ("2", "Price moves"),
        ("3", "Orders open"),
        ("4", "Stops and rearm"),
        ("5", "Close and restart"),
    ]
    gap = 16
    box_width = (width - gap * (len(labels) - 1)) / len(labels)
    box_height = 70
    y_bottom = y_top - box_height

    for index, (number, label) in enumerate(labels):
        box_x = x + index * (box_width + gap)
        pdf.setFillColor(WHITE)
        pdf.setStrokeColor(BORDER)
        pdf.roundRect(
            box_x, y_bottom, box_width, box_height, 7, stroke=1, fill=1
        )
        pdf.setFillColor(NAVY_2)
        pdf.circle(box_x + box_width / 2, y_top - 17, 10, stroke=0, fill=1)
        pdf.setFillColor(WHITE)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawCentredString(
            box_x + box_width / 2, y_top - 20, number
        )
        draw_paragraph(
            pdf,
            label,
            box_x + 6,
            y_top - 35,
            box_width - 12,
            CENTER_TINY,
            29,
        )
        if index < len(labels) - 1:
            draw_arrow(
                pdf,
                box_x + box_width + 2,
                y_bottom + box_height / 2,
                box_x + box_width + gap - 2,
            )


def draw_step_card(
    pdf: canvas.Canvas,
    x: float,
    y_top: float,
    width: float,
    height: float,
    number: int,
    title: str,
    body: str,
) -> None:
    y_bottom = y_top - height
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(BORDER)
    pdf.roundRect(x, y_bottom, width, height, 8, stroke=1, fill=1)
    pdf.setFillColor(NAVY_2)
    pdf.circle(x + 24, y_top - 25, 13, stroke=0, fill=1)
    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(x + 24, y_top - 28, str(number))
    draw_paragraph(
        pdf, title, x + 46, y_top - 17, width - 60, CARD_TITLE, 29
    )
    draw_paragraph(
        pdf,
        body,
        x + 16,
        y_top - 50,
        width - 32,
        BODY_SMALL,
        height - 59,
    )


def page_one(pdf: canvas.Canvas) -> None:
    draw_header(pdf, 1, "What This EA Does")

    draw_paragraph(
        pdf,
        "StraddleReplica is an automated gold trading EA for MT5. It places "
        "buy-stop orders above the current price and sell-stop orders below it. "
        "The aim is to join a strong move in either direction.",
        MARGIN,
        727,
        318,
        BODY,
        72,
    )

    pdf.setFillColor(GOLD_LIGHT)
    pdf.setStrokeColor(GOLD)
    pdf.roundRect(378, 632, 175, 99, 9, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 27)
    pdf.drawCentredString(465.5, 687, "about 92%")
    draw_paragraph(
        pdf,
        "estimated behavioral similarity",
        393,
        671,
        145,
        CENTER_SMALL,
        32,
    )

    draw_card(
        pdf,
        MARGIN,
        610,
        CONTENT_WIDTH,
        82,
        "In one sentence",
        "It builds a ladder of pending orders around gold, manages opened "
        "trades with protective stops, closes the trading basket, then starts "
        "a fresh ladder.",
        accent=GOLD,
        fill=LIGHT,
        body_style=BODY,
    )

    draw_section_label(pdf, "THE BASIC SHAPE", MARGIN, 501)
    card_gap = 10
    metric_width = (CONTENT_WIDTH - 2 * card_gap) / 3
    draw_metric(pdf, MARGIN, 474, metric_width, 87, "60", "pending orders at startup")
    draw_metric(
        pdf,
        MARGIN + metric_width + card_gap,
        474,
        metric_width,
        87,
        "30 + 30",
        "buy stops above and sell stops below",
    )
    draw_metric(
        pdf,
        MARGIN + 2 * (metric_width + card_gap),
        474,
        metric_width,
        87,
        "XAUUSD",
        "designed for gold on a hedging account",
    )

    draw_section_label(pdf, "WHAT THE EVIDENCE SUPPORTS", MARGIN, 359)
    draw_bullets(
        pdf,
        [
            "<b>46 of 46 observed grid deployments matched</b> the expected "
            "order sequence, spacing, and overall shape.",
            "The combined evidence supports <b>approximately 92%</b> overall "
            "behavioral similarity to the target EA.",
            "The stop pattern is estimated at about <b>95-97% confidence</b>, "
            "but it was reconstructed from trade history rather than source code.",
        ],
        MARGIN,
        331,
        CONTENT_WIDTH,
        style=BODY,
        gap=9,
    )

    draw_card(
        pdf,
        MARGIN,
        188,
        CONTENT_WIDTH,
        91,
        "Important: this is not proven 100% identical",
        "The original source code was not available. Broker prices, spread, "
        "slippage, order timing, and hidden target-EA rules can change real "
        "trades. The similarity figure is an engineering estimate, not a promise.",
        accent=RED,
        fill=RED_LIGHT,
        body_style=BODY,
    )

    draw_footer(pdf, 1)
    pdf.showPage()


def page_two(pdf: canvas.Canvas) -> None:
    draw_header(pdf, 2, "How the Grid Works")

    draw_paragraph(
        pdf,
        "Think of the grid as a price ladder. Buy orders wait above the starting "
        "price. Sell orders wait below it. A pending order becomes a live trade "
        "only when price reaches that level.",
        MARGIN,
        727,
        CONTENT_WIDTH,
        BODY,
        52,
    )

    draw_grid_diagram(pdf, MARGIN, 669, CONTENT_WIDTH, 280)

    draw_section_label(pdf, "LOT SIZE GROUPS", MARGIN, 365)
    gap = 10
    tier_width = (CONTENT_WIDTH - 2 * gap) / 3
    draw_card(
        pdf,
        MARGIN,
        338,
        tier_width,
        83,
        "Levels 1-10",
        "<b>0.01 lot</b><br/>Closest to the starting price.",
        accent=GREEN,
        fill=GREEN_LIGHT,
        body_style=CENTER_SMALL,
        title_style=ParagraphStyle(
            "TierTitle1", parent=CARD_TITLE, alignment=TA_CENTER
        ),
    )
    draw_card(
        pdf,
        MARGIN + tier_width + gap,
        338,
        tier_width,
        83,
        "Levels 11-20",
        "<b>0.06 lot</b><br/>Middle part of the ladder.",
        accent=GOLD,
        fill=GOLD_LIGHT,
        body_style=CENTER_SMALL,
        title_style=ParagraphStyle(
            "TierTitle2", parent=CARD_TITLE, alignment=TA_CENTER
        ),
    )
    draw_card(
        pdf,
        MARGIN + 2 * (tier_width + gap),
        338,
        tier_width,
        83,
        "Levels 21-30",
        "<b>0.15 lot</b><br/>Farthest and largest orders.",
        accent=RED,
        fill=RED_LIGHT,
        body_style=CENTER_SMALL,
        title_style=ParagraphStyle(
            "TierTitle3", parent=CARD_TITLE, alignment=TA_CENTER
        ),
    )

    draw_section_label(pdf, "THE DISTANCE BETWEEN LEVELS", MARGIN, 232)
    draw_paragraph(
        pdf,
        "The spacing changes with the gold price. When gold is higher, the "
        "distance becomes slightly wider. In the observed target pattern, the "
        "step was close to the starting gold price divided by 3,000.",
        MARGIN,
        205,
        CONTENT_WIDTH,
        BODY,
        52,
    )

    draw_card(
        pdf,
        MARGIN,
        147,
        CONTENT_WIDTH,
        70,
        "Pending does not mean open",
        "At startup there may be 60 waiting orders, but they are not all live "
        "positions. They open only as price travels through the ladder.",
        accent=BLUE,
        fill=BLUE_LIGHT,
        body_style=BODY_SMALL,
    )

    draw_footer(pdf, 2)
    pdf.showPage()


def page_three(pdf: canvas.Canvas) -> None:
    draw_header(pdf, 3, "How Trades Are Managed")

    draw_paragraph(
        pdf,
        "The EA treats each filled level as part of one larger trading basket. "
        "It mainly protects winners by changing stop-loss levels instead of "
        "using a separate take-profit on every trade.",
        MARGIN,
        727,
        CONTENT_WIDTH,
        BODY,
        52,
    )

    col_gap = 12
    col_width = (CONTENT_WIDTH - col_gap) / 2
    draw_card(
        pdf,
        MARGIN,
        661,
        col_width,
        124,
        "1. A pending order opens",
        "When gold touches a buy-stop or sell-stop level, that waiting order "
        "becomes an active market position.",
        accent=BLUE,
        fill=BLUE_LIGHT,
        body_style=BODY,
    )
    draw_card(
        pdf,
        MARGIN + col_width + col_gap,
        661,
        col_width,
        124,
        "2. First protective stop",
        "After price moves far enough in the trade's favor, the EA adds or "
        "moves a stop to reduce the risk on that position.",
        accent=GREEN,
        fill=GREEN_LIGHT,
        body_style=BODY,
    )
    draw_card(
        pdf,
        MARGIN,
        520,
        col_width,
        124,
        "3. Second profit lock",
        "If the move continues, the stop is moved again so more of the open "
        "profit is protected if price turns back.",
        accent=GOLD,
        fill=GOLD_LIGHT,
        body_style=BODY,
    )
    draw_card(
        pdf,
        MARGIN + col_width + col_gap,
        520,
        col_width,
        124,
        "4. The level can be rearmed",
        "After a stopped trade, the EA can place that level again after about "
        "one second, as long as the order price is valid.",
        accent=RED,
        fill=RED_LIGHT,
        body_style=BODY,
    )

    draw_card(
        pdf,
        MARGIN,
        376,
        CONTENT_WIDTH,
        142,
        "Basket close and restart",
        "The EA watches the group of trades as one basket. Near the observed "
        "target of about <b>$30</b>, it cancels remaining pending orders, closes "
        "positions, and prepares a new grid. The observed restart is usually "
        "about <b>two seconds</b> later.<br/><br/>Spread and slippage can make "
        "the final account result different from the target amount.",
        accent=GOLD,
        fill=LIGHT,
        body_style=BODY,
    )

    draw_card(
        pdf,
        MARGIN,
        207,
        CONTENT_WIDTH,
        105,
        "What is known and what is estimated",
        "The two-stage stop behavior is strongly supported by the trade "
        "history, with an estimated 95-97% match. The exact hidden calculation "
        "inside the original EA cannot be proven without its source code.",
        accent=BLUE,
        fill=BLUE_LIGHT,
        body_style=BODY,
    )

    draw_footer(pdf, 3)
    pdf.showPage()


def page_four(pdf: canvas.Canvas) -> None:
    draw_header(pdf, 4, "One Simple Trading Cycle")

    draw_paragraph(
        pdf,
        "A cycle starts when the EA creates a fresh grid and ends when that "
        "basket is closed. The EA then builds the next grid around a new "
        "starting price.",
        MARGIN,
        727,
        CONTENT_WIDTH,
        BODY,
        48,
    )

    draw_cycle_flow(pdf, MARGIN, 657, CONTENT_WIDTH)

    draw_section_label(pdf, "EXAMPLE IN SIMPLE TERMS", MARGIN, 560)
    draw_numbered_steps(
        pdf,
        [
            (
                "Build the ladder.",
                "The EA places 30 buy stops above gold and 30 sell stops below it.",
            ),
            (
                "Gold starts rising.",
                "The closest buy stops open one after another as price climbs.",
            ),
            (
                "Protect the winners.",
                "The EA moves stops on trades that have gained enough.",
            ),
            (
                "Reuse stopped levels.",
                "A stopped level may be placed again after the one-second gate.",
            ),
            (
                "Finish the basket.",
                "The EA cancels waiting orders and closes remaining positions.",
            ),
            (
                "Start again.",
                "A fresh grid is normally created about two seconds later.",
            ),
        ],
        MARGIN,
        530,
        CONTENT_WIDTH,
        style=BODY_SMALL,
        gap=7,
    )

    outcome_gap = 12
    outcome_width = (CONTENT_WIDTH - outcome_gap) / 2
    draw_card(
        pdf,
        MARGIN,
        291,
        outcome_width,
        127,
        "The usual winning pattern",
        "Many trades can close for small stop-locked gains while the move "
        "continues through the grid.",
        accent=GREEN,
        fill=GREEN_LIGHT,
        body_style=BODY,
    )
    draw_card(
        pdf,
        MARGIN + outcome_width + outcome_gap,
        291,
        outcome_width,
        127,
        "The important losing pattern",
        "A reversal or basket reset can close leftover trades together. One "
        "larger basket loss can follow many small wins.",
        accent=RED,
        fill=RED_LIGHT,
        body_style=BODY,
    )

    pdf.setFillColor(NAVY)
    pdf.roundRect(MARGIN, 96, CONTENT_WIDTH, 53, 7, stroke=0, fill=1)
    draw_paragraph(
        pdf,
        "<b>Key point:</b> a high percentage of winning trades does not remove "
        "the risk of a large losing basket.",
        MARGIN + 16,
        132,
        CONTENT_WIDTH - 32,
        ParagraphStyle("WhiteBody", parent=BODY, textColor=WHITE),
        34,
    )

    draw_footer(pdf, 4)
    pdf.showPage()


def page_five(pdf: canvas.Canvas) -> None:
    draw_header(pdf, 5, "Real-Account Installation")

    draw_paragraph(
        pdf,
        "These steps explain a manual MT5 setup. Menu names can vary slightly "
        "between brokers. The real preset allows live trading, so check every "
        "setting before you press OK.",
        MARGIN,
        727,
        CONTENT_WIDTH,
        BODY,
        52,
    )

    gap = 12
    step_width = (CONTENT_WIDTH - gap) / 2
    top_rows = [656, 540, 424]
    steps = [
        (
            1,
            "Install the EA",
            "In MT5 choose File > Open Data Folder. Put the supplied .ex5 file "
            "in MQL5/Experts, then refresh Navigator or restart MT5.",
        ),
        (
            2,
            "Open the gold chart",
            "Use your broker's gold symbol. It may be XAUUSD, XAUUSDm, GOLD, "
            "or another broker-specific name.",
        ),
        (
            3,
            "Check the account type",
            "The account must support hedging, meaning buy and sell positions "
            "can exist at the same time.",
        ),
        (
            4,
            "Check broker capacity",
            "The broker must allow at least 60 pending orders plus any open "
            "positions created during the cycle.",
        ),
        (
            5,
            "Attach and load",
            "Drag the EA onto the gold chart. In Inputs choose Load and select "
            "LATEST_30_REAL_EXACT.set.",
        ),
        (
            6,
            "Start and watch",
            "Enable Algo Trading, press OK, and confirm that the first grid "
            "appears without order errors in the Experts or Journal tab.",
        ),
    ]
    for index, step in enumerate(steps):
        row = index // 2
        column = index % 2
        draw_step_card(
            pdf,
            MARGIN + column * (step_width + gap),
            top_rows[row],
            step_width,
            101,
            step[0],
            step[1],
            step[2],
        )

    draw_card(
        pdf,
        MARGIN,
        298,
        CONTENT_WIDTH,
        112,
        "Live-account settings in the real preset",
        "<b>RequireDemoAccount=false</b> means the EA is allowed to run on a "
        "real account.<br/><b>SafetyEnabled=false</b> means the optional safety "
        "layer is disabled. Do not mistake this setting for account protection.",
        accent=RED,
        fill=RED_LIGHT,
        body_style=BODY,
    )

    draw_card(
        pdf,
        MARGIN,
        164,
        CONTENT_WIDTH,
        77,
        "Strongly recommended before live money",
        "Run the same broker, symbol, and preset on demo first. Then use only "
        "capital you can afford to lose and confirm that margin remains "
        "comfortable when several larger outer levels open.",
        accent=GOLD,
        fill=GOLD_LIGHT,
        body_style=BODY_SMALL,
    )

    draw_footer(pdf, 5)
    pdf.showPage()


def page_six(pdf: canvas.Canvas) -> None:
    draw_header(pdf, 6, "Risks and Operating Checklist")

    draw_paragraph(
        pdf,
        "This EA can build exposure quickly. Real-account results depend on the "
        "broker and the market, not only on the EA logic.",
        MARGIN,
        727,
        CONTENT_WIDTH,
        BODY,
        42,
    )

    risk_gap = 10
    risk_width = (CONTENT_WIDTH - risk_gap) / 2
    risks = [
        (
            "Fast exposure growth",
            "Outer grid orders are 0.15 lot each. Several fills can increase "
            "margin use quickly.",
        ),
        (
            "Gold can jump",
            "News, gaps, and fast moves can skip expected prices or trigger "
            "many levels in a short time.",
        ),
        (
            "Execution can differ",
            "Spread, slippage, latency, rejected orders, and stop levels vary "
            "between brokers.",
        ),
        (
            "Basket losses can be large",
            "Many small wins can be followed by one larger close of leftover "
            "positions.",
        ),
        (
            "Broker limits matter",
            "Order-count limits, minimum distance rules, and symbol settings "
            "can prevent an exact grid.",
        ),
        (
            "Extra safety is off",
            "The real preset uses SafetyEnabled=false. Have your own loss and "
            "shutdown plan.",
        ),
    ]
    row_tops = [665, 570, 475]
    for index, (title, body) in enumerate(risks):
        row = index // 2
        column = index % 2
        draw_card(
            pdf,
            MARGIN + column * (risk_width + risk_gap),
            row_tops[row],
            risk_width,
            82,
            title,
            body,
            accent=RED if index in (1, 3, 5) else GOLD,
            fill=WHITE,
            body_style=BODY_SMALL,
        )

    draw_section_label(pdf, "BEFORE STARTING", MARGIN, 367, 250)
    draw_section_label(pdf, "KEEP THESE RECORDS", 318, 367, 235)
    draw_bullets(
        pdf,
        [
            "Correct gold symbol and chart.",
            "Hedging account confirmed.",
            "At least 60 pending orders allowed.",
            "Preset name and inputs checked.",
            "Enough free margin and a manual stop plan.",
        ],
        MARGIN,
        338,
        240,
        style=BODY_SMALL,
        gap=5,
        bullet_color=GREEN,
    )
    draw_bullets(
        pdf,
        [
            "Experts and Journal logs.",
            "Account history and broker statements.",
            "Screenshots of unusual cycles.",
            "Spread, rejection, and slippage notes.",
            "Any broker symbol-rule changes.",
        ],
        318,
        338,
        235,
        style=BODY_SMALL,
        gap=5,
        bullet_color=BLUE,
    )

    draw_card(
        pdf,
        MARGIN,
        183,
        CONTENT_WIDTH,
        96,
        "Final truth about the match",
        "The EA is estimated at <b>approximately 92%</b> behavioral similarity. "
        "It is not proven 100% identical, and that percentage does not guarantee "
        "the same trades or profit on a real account. Monitor every live cycle.",
        accent=GOLD,
        fill=GOLD_LIGHT,
        body_style=BODY,
    )

    draw_footer(pdf, 6)
    pdf.showPage()


def build_pdf(output_path: str | Path) -> Path:
    """Build the guide and return its resolved output path."""
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(
        str(output),
        pagesize=A4,
        pageCompression=1,
    )
    pdf.setTitle("StraddleReplica EA Simple Guide")
    pdf.setAuthor("StraddleReplica EA project")
    pdf.setSubject("Plain-English operation, installation, and risk guide")

    for page in (page_one, page_two, page_three, page_four, page_five, page_six):
        page(pdf)

    pdf.save()
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the six-page StraddleReplica EA simple guide."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pdf/StraddleReplica_EA_Simple_Guide.pdf"),
        help="Destination PDF path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = build_pdf(args.output)
    size_kb = output.stat().st_size / 1024
    print(f"Created {output} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
