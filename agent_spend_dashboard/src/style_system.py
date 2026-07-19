"""
style_system.py

Visual Design System & CSS injections for ADK Agent Spend Dashboard.
Aligns Streamlit output to the premium, clean, card-based look of Design.html.
"""

CSS_STYLES = """
<style>
/* ── HIDE STREAMLIT CHROME ── */
header[data-testid="stHeader"], footer, [data-testid="stToolbar"], .stDeployButton {
    display: none !important;
}

/* ── GLOBAL BODY STYLING ── */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], section[data-testid="stMain"] {
    background-color: oklch(0.975 0.004 250) !important;
    color: oklch(0.2 0.01 250) !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

.block-container {
    padding: 2.5rem 3rem 4rem !important;
    max-width: 1400px !important;
}

/* ── SIDEBAR STYLING ── */
section[data-testid="stSidebar"] {
    background-color: oklch(1 0 0) !important;
    border-right: 1px solid oklch(0.9 0.006 250) !important;
    padding: 2rem 1.25rem !important;
}
section[data-testid="stSidebar"] * {
    color: oklch(0.2 0.01 250) !important;
}
section[data-testid="stSidebar"] .stSelectbox label, 
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stMultiSelect label {
    font-size: 12.5px !important;
    font-weight: 600 !important;
    color: oklch(0.35 0.01 250) !important;
    text-transform: capitalize !important;
}
section[data-testid="stSidebar"] select, 
section[data-testid="stSidebar"] input {
    border: 1px solid oklch(0.88 0.006 250) !important;
    border-radius: 8px !important;
    background: oklch(0.99 0.002 250) !important;
    color: oklch(0.2 0.01 250) !important;
}

/* ── CARD LAYOUT CONTAINER ── */
.dashboard-card {
    background-color: white !important;
    border: 1px solid oklch(0.91 0.006 250) !important;
    border-radius: 14px !important;
    padding: 24px 26px !important;
    margin-bottom: 22px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
}
.dashboard-card-title {
    font-size: 15px !important;
    font-weight: 700 !important;
    color: oklch(0.2 0.01 250) !important;
    margin-bottom: 4px !important;
}
.dashboard-card-subtitle {
    font-size: 12.5px !important;
    color: oklch(0.55 0.01 250) !important;
    margin-bottom: 18px !important;
}

/* ── HERO TOTAL CARD ── */
.hero-card {
    background: linear-gradient(135deg, oklch(0.55 0.15 250), oklch(0.5 0.14 265)) !important;
    border-radius: 16px !important;
    padding: 28px 32px !important;
    color: white !important;
    box-shadow: 0 8px 24px oklch(0.55 0.15 250 / 0.18) !important;
    margin-bottom: 22px !important;
}
.hero-card-label {
    font-size: 12.5px !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    opacity: 0.8 !important;
}
.hero-card-value {
    font-size: 44px !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    font-family: 'Roboto Mono', ui-monospace, monospace !important;
    margin-top: 4px !important;
}

/* ── DATA TABLES ── */
.data-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 0.8rem;
}
.data-table th {
    text-align: left;
    padding: 0.6rem 0.8rem;
    color: oklch(0.55 0.01 250);
    font-weight: 500;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid oklch(0.91 0.006 250);
}
.data-table td {
    padding: 0.65rem 0.8rem;
    color: oklch(0.2 0.01 250);
    border-bottom: 1px solid oklch(0.95 0.006 250);
}
.data-table tr:last-child td {
    border-bottom: none;
}

/* Custom expanders override */
.streamlit-expanderHeader {
    background-color: white !important;
    border: 1px solid oklch(0.91 0.006 250) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}
</style>
"""

SIDEBAR_BRAND_HTML = """
<div style="display:flex; align-items:center; gap:10px; margin-bottom: 28px;">
  <div style="width:32px; height:32px; border-radius:8px; background:oklch(0.55 0.15 250); display:flex; align-items:center; justify-content:center; flex:none;">
    <div style="width:14px; height:14px; border-radius:3px; background:white;"></div>
  </div>
  <div>
    <div style="font-size:15px; font-weight:700; letter-spacing:-0.01em; line-height:1.2; color:oklch(0.2 0.01 250);">ADK Spend</div>
    <div style="font-size:11.5px; color:oklch(0.55 0.01 250); line-height:1.2;">Agent cost analytics</div>
  </div>
</div>
<div style="font-size:11px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; color:oklch(0.55 0.01 250); margin-bottom: 10px;">Filters</div>
"""

def render_hero_card(total_cost, total_compute, total_tokens_c, total_requests, period_label):
    return f"""
    <div class="hero-card">
      <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:20px; width:100%;">
        <div>
          <div class="hero-card-label">Total spend · {period_label}</div>
          <div class="hero-card-value">${total_cost:,.2f}</div>
        </div>
        <div style="display:flex; gap:36px; flex-wrap:wrap;">
          <div style="display:flex; flex-direction:column; gap:4px;">
            <div style="font-size:11.5px; opacity:0.8; font-weight:600; letter-spacing:0.04em; text-transform:uppercase;">Compute Cost</div>
            <div style="font-size:18px; font-weight:700; font-family:'Roboto Mono', ui-monospace, monospace;">${total_compute:,.2f}</div>
          </div>
          <div style="display:flex; flex-direction:column; gap:4px;">
            <div style="font-size:11.5px; opacity:0.8; font-weight:600; letter-spacing:0.04em; text-transform:uppercase;">Token Cost</div>
            <div style="font-size:18px; font-weight:700; font-family:'Roboto Mono', ui-monospace, monospace;">${total_tokens_c:,.2f}</div>
          </div>
          <div style="display:flex; flex-direction:column; gap:4px;">
            <div style="font-size:11.5px; opacity:0.8; font-weight:600; letter-spacing:0.04em; text-transform:uppercase;">Total Requests</div>
            <div style="font-size:18px; font-weight:700; font-family:'Roboto Mono', ui-monospace, monospace;">{total_requests:,.0f}</div>
          </div>
        </div>
      </div>
    </div>
    """

def render_card_start(title, subtitle=None):
    subtitle_html = f'<div class="dashboard-card-subtitle">{subtitle}</div>' if subtitle else ''
    return f"""
    <div class="dashboard-card">
      <div class="dashboard-card-title">{title}</div>
      {subtitle_html}
    """

def render_card_end():
    return "</div>"
