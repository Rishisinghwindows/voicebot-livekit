"""Generate UBudy Cost Report PDF"""
from fpdf import FPDF
from datetime import date

class Report(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(100, 100, 255)
        self.cell(0, 8, "UBudy", align="L")
        self.set_text_color(150, 150, 150)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 8, "Confidential", align="R")
        self.ln(10)
        self.set_draw_color(100, 100, 255)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"UBudy Voice Bot - Cost Report | Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.ln(4)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(50, 50, 50)
        self.cell(0, 10, title)
        self.ln(8)

    def sub_title(self, title):
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 7, title)
        self.ln(7)

    def body_text(self, text):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5, text)
        self.ln(2)

    def add_table(self, headers, data, col_widths, header_color=(100, 100, 255)):
        # Header
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(*header_color)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=0, fill=True, align="C")
        self.ln()
        # Rows
        self.set_font("Helvetica", "", 8)
        self.set_text_color(50, 50, 50)
        fill = False
        for row in data:
            if fill:
                self.set_fill_color(245, 245, 255)
            else:
                self.set_fill_color(255, 255, 255)
            for i, val in enumerate(row):
                align = "L" if i == 0 else "R" if i == len(row) - 1 else "C"
                self.cell(col_widths[i], 6.5, str(val), border=0, fill=True, align=align)
            self.ln()
            fill = not fill
        self.ln(3)

    def highlight_box(self, text, color=(100, 100, 255)):
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 12, f"  {text}", fill=True, align="L")
        self.ln(14)
        self.set_text_color(50, 50, 50)


pdf = Report()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# Title
pdf.set_font("Helvetica", "B", 22)
pdf.set_text_color(50, 50, 50)
pdf.cell(0, 15, "UBudy Voice Bot", align="C")
pdf.ln(12)
pdf.set_font("Helvetica", "", 12)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 8, "Cost Estimation Report", align="C")
pdf.ln(8)
pdf.set_font("Helvetica", "", 9)
pdf.cell(0, 6, f"Date: {date.today().strftime('%d %B %Y')}", align="C")
pdf.ln(6)
pdf.cell(0, 6, "AI-Powered Mental Health Voice Companion", align="C")
pdf.ln(12)

# Executive Summary
pdf.section_title("1. Executive Summary")
pdf.body_text(
    "UBudy is an AI-powered voice bot that provides compassionate mental health support "
    "through real-time voice conversations. It supports both Hindi and English, using "
    "state-of-the-art speech recognition, AI language models, and natural text-to-speech "
    "technology. This report provides a detailed cost breakdown for operating the bot."
)

pdf.highlight_box("Total Cost:  Rs 2.36 per minute  |  Rs 11.80 per 5-min call")

# Technology Stack
pdf.section_title("2. Technology Stack")
pdf.add_table(
    ["Component", "Provider", "Technology", "Purpose"],
    [
        ["Speech-to-Text", "Deepgram", "Nova-2 (Hindi)", "Convert user voice to text"],
        ["AI Brain (LLM)", "OpenAI", "GPT-4o-mini", "Generate empathetic responses"],
        ["Text-to-Speech", "OpenAI", "TTS-1 (nova)", "Convert text to natural voice"],
        ["Infrastructure", "LiveKit", "Cloud (Audio)", "Real-time audio streaming"],
    ],
    [48, 38, 48, 56],
)

# Cost Breakdown
pdf.section_title("3. Detailed Cost Breakdown (Per Minute)")
pdf.add_table(
    ["Service", "Rate", "Usage/min", "Cost/min (USD)", "Cost/min (INR)"],
    [
        ["Deepgram STT", "$0.0058/min", "1 min audio", "$0.0058", "Rs 0.49"],
        ["OpenAI GPT-4o-mini", "$0.15-0.60/1M tokens", "~2,670 tokens", "$0.0005", "Rs 0.04"],
        ["OpenAI TTS-1", "$15/1M chars", "~750 chars", "$0.0113", "Rs 0.95"],
        ["LiveKit Cloud", "$0.0105/min", "1 agent session", "$0.0105", "Rs 0.88"],
        ["TOTAL", "", "", "$0.0281", "Rs 2.36"],
    ],
    [36, 40, 34, 36, 34],
)

# Cost share
pdf.sub_title("Cost Distribution")
pdf.add_table(
    ["Service", "Share of Total Cost"],
    [
        ["OpenAI TTS (Voice Generation)", "41%"],
        ["LiveKit Cloud (Infrastructure)", "38%"],
        ["Deepgram STT (Speech Recognition)", "21%"],
        ["OpenAI LLM (AI Processing)", "<2%"],
    ],
    [100, 80],
)

# Monthly Projections
pdf.section_title("4. Monthly Cost Projections (INR)")
pdf.add_table(
    ["Scenario", "Calls/Day", "Avg Duration", "Cost/Call", "Daily Cost", "Monthly Cost"],
    [
        ["Starter", "10", "5 min", "Rs 11.80", "Rs 118", "Rs 3,540"],
        ["Growth", "50", "5 min", "Rs 11.80", "Rs 590", "Rs 17,700"],
        ["Business", "100", "5 min", "Rs 11.80", "Rs 1,180", "Rs 35,400"],
        ["Business+", "100", "10 min", "Rs 23.60", "Rs 2,360", "Rs 70,800"],
        ["Enterprise", "500", "5 min", "Rs 11.80", "Rs 5,900", "Rs 1,77,000"],
        ["Enterprise+", "500", "10 min", "Rs 23.60", "Rs 11,800", "Rs 3,54,000"],
    ],
    [28, 24, 26, 26, 30, 36],
)
pdf.body_text("* Monthly = Daily x 30 days. All prices in INR at exchange rate of $1 = Rs 84.")

# Annual Projections
pdf.add_page()
pdf.section_title("5. Annual Cost Projections (INR)")
pdf.add_table(
    ["Scenario", "Monthly", "Annual", "Annual (USD)"],
    [
        ["Starter (10 calls/day)", "Rs 3,540", "Rs 42,480", "$506"],
        ["Growth (50 calls/day)", "Rs 17,700", "Rs 2,12,400", "$2,529"],
        ["Business (100 calls/day)", "Rs 35,400", "Rs 4,24,800", "$5,057"],
        ["Business+ (100 calls/day x 10m)", "Rs 70,800", "Rs 8,49,600", "$10,114"],
        ["Enterprise (500 calls/day)", "Rs 1,77,000", "Rs 21,24,000", "$25,286"],
    ],
    [55, 40, 45, 40],
)

# Free Tiers
pdf.section_title("6. Free Tiers & Initial Savings")
pdf.add_table(
    ["Provider", "Free Tier", "Equivalent Value"],
    [
        ["Deepgram", "$200 credit", "~34,000 minutes of STT"],
        ["LiveKit", "1,000 agent mins + 5,000 WebRTC mins/month", "~Rs 840/month saved"],
        ["OpenAI", "$5 credit for new accounts", "~444 minutes of TTS"],
    ],
    [45, 75, 60],
)
pdf.body_text(
    "For the first few months, the free tiers from Deepgram and LiveKit can significantly "
    "reduce costs. Deepgram's $200 credit alone covers approximately 34,000 minutes of "
    "speech recognition."
)

# Volume Discounts
pdf.section_title("7. Volume Discounts & Optimization")
pdf.add_table(
    ["Optimization", "Current Rate", "Optimized Rate", "Savings"],
    [
        ["Deepgram Growth Plan ($4K/yr)", "$0.0058/min", "$0.0047/min", "19% on STT"],
        ["LiveKit Scale Plan ($500/mo)", "$0.01/agent-min", "50K mins included", "Up to 40%"],
        ["Cached LLM prompts (OpenAI)", "$0.15/1M tokens", "$0.075/1M tokens", "50% on LLM"],
    ],
    [55, 35, 40, 40],
)

pdf.highlight_box("Optimized Cost:  Rs 1.85/min  (22% savings at scale)", color=(0, 170, 130))

# Assumptions
pdf.section_title("8. Assumptions")
pdf.body_text(
    "- 3 conversational exchanges per minute\n"
    "- User speaks ~100 words/minute (~130 tokens)\n"
    "- Agent responds ~50 words per response (~250 characters)\n"
    "- ~750 characters of TTS generated per minute\n"
    "- ~2,475 input + 195 output tokens to LLM per minute\n"
    "- System prompt: ~500 tokens (sent with each request)\n"
    "- Audio-only mode (no video)\n"
    "- Exchange rate: $1 = Rs 84\n"
    "- 30 days per month for projections"
)

# Sources
pdf.section_title("9. Pricing Sources")
pdf.set_font("Helvetica", "", 8)
pdf.set_text_color(80, 80, 80)
sources = [
    "Deepgram Pricing - https://deepgram.com/pricing",
    "OpenAI API Pricing - https://openai.com/api/pricing/",
    "LiveKit Cloud Pricing - https://livekit.io/pricing",
    "LiveKit Blog (Pricing Model) - https://blog.livekit.io/towards-a-future-aligned-pricing-model/",
]
for s in sources:
    pdf.cell(0, 5, f"  {s}")
    pdf.ln(5)

pdf.ln(8)
pdf.set_font("Helvetica", "I", 8)
pdf.set_text_color(150, 150, 150)
pdf.cell(0, 5, f"Report generated on {date.today().strftime('%d %B %Y')}. Prices subject to change by providers.", align="C")

output_path = "/Users/rishi/Downloads/voicebot/UBudy_Cost_Report.pdf"
pdf.output(output_path)
print(f"PDF saved: {output_path}")
