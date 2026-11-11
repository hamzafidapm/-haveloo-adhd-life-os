"""Build Quick_Start_Guide.pdf — the ONLY Etsy deliverable file.

Haveloo branding, Sage Calm colours. The "Open my planner" link is a
clearly-marked PLACEHOLDER — there is no live URL yet. Paste the real
Streamlit Cloud app URL into the placeholder box before listing, then
re-run this script. Never invent a URL here.

Run:  python3 build_guide.py
Out:  Quick_Start_Guide.pdf  (US Letter)
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Quick_Start_Guide.pdf")

SAGE = colors.HexColor("#6FA287")
SAGE_DARK = colors.HexColor("#4E7A63")
CREAM = colors.HexColor("#F7F3EC")
DARK = colors.HexColor("#2E2118")
MUTED = colors.HexColor("#6B5646")
LIGHT_SAGE_BG = colors.HexColor("#EAF3EC")
BORDER = colors.HexColor("#D8CFC2")

title_style = ParagraphStyle("Title2", fontName="Helvetica-Bold", fontSize=26,
                             leading=30, textColor=DARK, spaceAfter=6)
subtitle_style = ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=13,
                                leading=18, textColor=MUTED, spaceAfter=4)
h2_style = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=15,
                          leading=19, textColor=SAGE_DARK, spaceBefore=14, spaceAfter=6)
body_style = ParagraphStyle("Body", fontName="Helvetica", fontSize=11.5,
                            leading=17, textColor=DARK, spaceAfter=6)
small_style = ParagraphStyle("Small", fontName="Helvetica", fontSize=10,
                             leading=14, textColor=MUTED, spaceAfter=4)
step_num = ParagraphStyle("StepNum", fontName="Helvetica-Bold", fontSize=15,
                          leading=19, textColor=SAGE_DARK)
step_body = ParagraphStyle("StepBody", fontName="Helvetica", fontSize=11.5,
                           leading=17, textColor=DARK)
placeholder_style = ParagraphStyle("Placeholder", fontName="Helvetica-Bold",
                                   fontSize=12, leading=16, textColor=DARK,
                                   alignment=1)
note_style = ParagraphStyle("Note", fontName="Helvetica", fontSize=10.5,
                            leading=15, textColor=DARK)


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(SAGE)
    canvas.rect(0, LETTER[1] - 0.55 * inch, LETTER[0], 0.55 * inch, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(0.75 * inch, LETTER[1] - 0.38 * inch, "HAVELOO")
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(LETTER[0] - 0.75 * inch, LETTER[1] - 0.38 * inch,
                           "ADHD Life OS  •  Quick Start Guide")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8.5)
    canvas.drawCentredString(LETTER[0] / 2, 0.55 * inch,
                             "Haveloo  •  ADHD Life OS  •  Page %d" % doc.page)
    canvas.restoreState()


def step(num, title, text):
    t = Table([
        [Paragraph(f"<b>{num}</b>", step_num),
         Paragraph(f"<b>{title}</b><br/>{text}", step_body)],
    ], colWidths=[0.45 * inch, 6.3 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def bullet(text):
    return Paragraph(f"•&nbsp;&nbsp;{text}", body_style)


def build():
    doc = SimpleDocTemplate(
        OUT, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.85 * inch, bottomMargin=0.8 * inch,
        title="Haveloo ADHD Life OS — Quick Start Guide",
        author="Haveloo",
    )
    story = []
    story.append(Paragraph("Haveloo ADHD Life OS", title_style))
    story.append(Paragraph("Quick Start Guide", ParagraphStyle(
        "Title2b", parent=title_style, textColor=SAGE_DARK)))
    story.append(Paragraph(
        "Your neuro-adaptive planner — tasks, focus, habits and calm, in one place. "
        "This guide is the only file you need: your planner opens in your browser, "
        "on any device. No app to install, no codes to copy, no keys to keep.",
        subtitle_style))
    story.append(Spacer(1, 6))

    # ---- Open my planner placeholder box ----
    box = Table([
        [Paragraph("OPEN MY PLANNER", ParagraphStyle(
            "BoxHead", fontName="Helvetica-Bold", fontSize=10, leading=13,
            textColor=SAGE_DARK, alignment=1))],
        [Paragraph("YOUR APP LINK — paste your Streamlit Cloud app URL here before listing",
                   placeholder_style)],
        [Paragraph("Tap the link above to open your planner. It will look like "
                   "https://your-app-name.streamlit.app — your real link goes here, "
                   "not a sample.", ParagraphStyle(
                       "BoxSmall", parent=small_style, alignment=1))],
    ], colWidths=[6.9 * inch])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_SAGE_BG),
        ("BOX", (0, 0), (-1, -1), 1.2, SAGE),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(box)

    story.append(Paragraph("HOW YOU GET IT (instant access)", h2_style))
    story.append(step(1, "Download the Quick Start Guide (PDF) from your Etsy purchase.",
                      "This PDF is your proof of purchase and your way in. Keep it somewhere safe."))
    story.append(step(2, "Tap “Open my planner”.",
                      "The link in the box above opens your planner in your browser — "
                      "iPhone, iPad, Android, Mac, Windows or Chromebook."))
    story.append(step(3, "Create your account with your email and a password.",
                      "Choose any password of 8 characters or more. Your password is stored "
                      "as a secure one-way hash — never in plain text."))
    story.append(step(4, "Unlock it with your Etsy order number — about 2 minutes, once only, "
                         "then just log in on any other device.",
                      "Find your order number in your Etsy purchase confirmation email. "
                      "Enter it once, and your planner is unlocked for life. "
                      "No codes to copy, no keys to keep."))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>About unlocking, honestly:</b> your order number is recorded for seller "
        "verification — Haveloo checks your order number against Etsy orders. "
        "Live automatic Etsy verification is not connected in this version.",
        ParagraphStyle("Honest", parent=note_style, backColor=LIGHT_SAGE_BG,
                       borderPadding=(8, 8, 8), spaceBefore=6, spaceAfter=6)))

    story.append(Paragraph("What you get", h2_style))
    for b in [
        "<b>Lifetime access</b> — pay once, use it for life. No subscription, no monthly fee.",
        "<b>Free updates</b> — when Haveloo improves the planner, you get the new version free.",
        "<b>6 themes in one picker</b> — Cocoa, Sage, Apricot, Lavender, Ocean and Rosewood. "
        "Each theme's colours and behaviour match its purpose, from calm to deep focus. "
        "Themes are supportive design only — they are not medical advice and do not treat anxiety or low mood.",
        "<b>Your data follows you</b> — log in on any device and see the same tasks, habits, "
        "focus sessions and rewards. Keep a JSON backup from inside the planner, too.",
    ]:
        story.append(bullet(b))

    story.append(Paragraph("Your devices", h2_style))
    story.append(Paragraph(
        "iPhone • iPad • Android • Mac • Windows • Chromebook — anything with a web "
        "browser. Your planner is a web app, so there is nothing to install and "
        "nothing to update by hand.", body_style))

    story.append(Paragraph("Need help?", h2_style))
    story.append(Paragraph(
        "Message Haveloo on Etsy and include your Etsy order number — we will help you "
        "get in. If you ever forget your password, message us from the email address "
        "on your account.", body_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Paragraph(
        "Thank you for choosing Haveloo. Small steps count — start with just your top 3 today.",
        ParagraphStyle("Thanks", parent=small_style, alignment=1, spaceBefore=6)))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print("Wrote", OUT)


if __name__ == "__main__":
    build()
