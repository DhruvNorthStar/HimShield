"""Presentation components used only by the HimShield dashboard.

No shared Streamlit settings, model inputs or saved artifacts are changed here.
Containers use Streamlit's documented key classes rather than generated CSS names.
"""
from base64 import b64encode
from html import escape
from pathlib import Path

import streamlit as st

# Existing map previews use NAVY; keep their rendered boundary pixels stable.
NAVY = "#102A43"
PRIMARY = "#0F2D46"
TEAL = "#0E7C86"
BACKGROUND = "#F6F8FA"
SURFACE = "#FFFFFF"
TEXT = "#172B4D"
SECONDARY = "#5B6B79"
BORDER = "#D9E2E8"
NAV_ACTIVE_BACKGROUND = "#E7F3E9"
NAV_ACTIVE_HOVER = "#D9ECDF"
NAV_ACTIVE_TEXT = "#1E5A36"
NAV_ACTIVE_ACCENT = "#2D7548"
MODEL_ACCENTS = {"SVM (RBF)": ("svm", "#2B6CB0"),
                 "Random Forest": ("rf", TEAL), "XGBoost": ("xgb", "#7C3AED")}

BENCHMARK_NOTE = (
    "Original random held-out benchmark. Separate spatial/control validation results "
    "and limitations are in Methodology & Validation when available."
)
THRESHOLD_NOTE = (
    "Youden thresholds were selected on the held-out test set. They are retrospective benchmark "
    "thresholds, not independently validated deployment thresholds."
)
SCORE_NOTE = (
    "Susceptibility scores rank model outputs; they are not calibrated probabilities of a landslide "
    "occurring. Low susceptibility does not guarantee safety."
)


def percent(value: float) -> str:
    """Format one original 0–1 classification metric; never change its stored value."""
    return f"{value:.2%}"


def percentage_points(value: float) -> str:
    """Differences between 0–1 metrics use percentage points, not relative percent change."""
    return f"{value * 100:+.2f} pp"


# :has gates even the application background to this dashboard's own marker.
# Owned key classes and semantic/test-id selectors keep styling independent of
# generated class names. The shared Streamlit theme and saved figures stay intact.
CSS = f"""
<style>
.stApp:has(.himshield-theme) {{
  --hs-accent: {TEAL};
  background: {BACKGROUND}; color: {TEXT};
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.stApp:has(.himshield-theme) [data-testid="stMainBlockContainer"] {{
  max-width: 1500px; padding-top: 2.75rem; padding-bottom: 4rem;
}}
.stApp:has(.himshield-theme) h2,
.stApp:has(.himshield-theme) h3 {{
  color: {PRIMARY}; letter-spacing: -.025em; line-height: 1.3;
}}
.stApp:has(.himshield-theme) h2 {{ font-size: 1.45rem; }}
.stApp:has(.himshield-theme) h3 {{ font-size: 1.15rem; }}
.stApp:has(.himshield-theme) [data-testid="stCaptionContainer"],
.stApp:has(.himshield-theme) [data-testid="stCaptionContainer"] p {{
  color: {SECONDARY}; line-height: 1.6; opacity: 1;
}}
.stApp:has(.himshield-theme) [data-testid="stSidebar"] {{
  background: {SURFACE}; border-right: 1px solid {BORDER};
}}
.st-key-himshield-navigation {{ gap: .4rem; }}
.st-key-himshield-navigation [data-testid="stPageLink-NavLink"] {{
  border-radius: .65rem; padding: .7rem .65rem; border: 1px solid transparent;
  color: {SECONDARY}; align-items: flex-start; height: auto;
}}
.st-key-himshield-navigation [data-testid="stPageLink-NavLink"] p {{
  white-space: normal; overflow-wrap: anywhere; font-size: .87rem; line-height: 1.45; color: inherit;
}}
.st-key-himshield-navigation [data-testid="stPageLink-NavLink"]:hover {{
  background: {BACKGROUND}; color: {PRIMARY};
}}
.st-key-himshield-nav-active [data-testid="stPageLink-NavLink"] {{
  background: {NAV_ACTIVE_BACKGROUND}; border-color: #BED8C7; color: {NAV_ACTIVE_TEXT};
  box-shadow: inset 3px 0 0 {NAV_ACTIVE_ACCENT};
}}
.st-key-himshield-nav-active [data-testid="stPageLink-NavLink"]:hover {{
  background: {NAV_ACTIVE_HOVER}; color: {NAV_ACTIVE_TEXT};
}}
.stApp:has(.himshield-theme) .st-key-himshield-navigation [data-testid="stPageLink-NavLink"]:focus-visible {{
  outline: 2px solid {NAV_ACTIVE_ACCENT}; outline-offset: 2px;
}}
.st-key-himshield-nav-active p {{ font-weight: 650; }}
.st-key-himshield-sidebar-meta {{
  border-top: 1px solid {BORDER}; margin-top: 1rem; padding-top: 1rem; gap: .65rem;
}}
.st-key-himshield-sidebar-meta [data-testid="stCaptionContainer"] {{ font-size: .76rem; }}
.st-key-himshield-sidebar-meta code {{ color: {SECONDARY}; background: {BACKGROUND}; }}
.st-key-himshield-header {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-left: 4px solid {TEAL};
  border-radius: 1rem; padding: 1.65rem 1.85rem; margin-bottom: .5rem;
  box-shadow: 0 3px 16px rgba(15, 45, 70, .035); gap: .65rem;
}}
.st-key-himshield-header h1 {{
  color: {PRIMARY}; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: clamp(1.9rem, 3vw, 2.75rem); font-weight: 750;
  line-height: 1.15; letter-spacing: -.045em; padding-top: 0; padding-bottom: .25rem;
}}
.st-key-himshield-header p {{ color: {SECONDARY}; line-height: 1.65; }}
[class*="st-key-himshield-panel-"] {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: .9rem;
  padding: 1.35rem; color: {TEXT}; min-width: 0; box-sizing: border-box;
  box-shadow: 0 3px 14px rgba(15, 45, 70, .035);
}}
[class*="st-key-himshield-panel-"] h2,
[class*="st-key-himshield-panel-"] h3 {{ color: {PRIMARY}; }}
[class*="st-key-himshield-panel-"][class*="-tone-svm"] {{ --hs-accent: {MODEL_ACCENTS['SVM (RBF)'][1]}; }}
[class*="st-key-himshield-panel-"][class*="-tone-rf"] {{ --hs-accent: {TEAL}; }}
[class*="st-key-himshield-panel-"][class*="-tone-xgb"] {{ --hs-accent: {MODEL_ACCENTS['XGBoost'][1]}; }}
[class*="st-key-himshield-panel-metric-"],
[class*="st-key-himshield-panel-prediction-"] {{
  border-top: 3px solid var(--hs-accent); font-variant-numeric: tabular-nums;
  padding: 1.15rem; min-width: 0;
}}
[class*="st-key-himshield-panel-metric-"] [data-testid="stCaptionContainer"] {{
  font-size: .8rem; font-weight: 550; min-height: 2.6em;
}}
.stApp:has(.himshield-theme) [data-testid="stMetricValue"] {{
  color: {PRIMARY}; font-size: clamp(1.6rem, 2.4vw, 2.15rem); font-weight: 700;
  letter-spacing: -.035em; line-height: 1.2;
}}
.stApp:has(.himshield-theme) [data-testid="stMetricLabel"] {{ color: {SECONDARY}; }}
.stApp:has(.himshield-theme) [data-testid="stTable"] {{
  overflow-x: auto; border: 1px solid {BORDER}; border-radius: .65rem;
}}
.stApp:has(.himshield-theme) [data-testid="stTable"] table {{
  width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums;
}}
.stApp:has(.himshield-theme) [data-testid="stTable"] th {{
  background: #EDF3F6; color: {PRIMARY}; font-weight: 650;
}}
.stApp:has(.himshield-theme) [data-testid="stTable"] :is(th, td) {{
  padding: .8rem .9rem; border-color: {BORDER}; line-height: 1.5;
}}
.stApp:has(.himshield-theme) [data-testid="stDataFrame"] {{
  border-radius: .65rem; border: 1px solid {BORDER}; overflow: hidden;
}}
.stApp:has(.himshield-theme) :is(button, input, [role="combobox"]) {{ font-family: inherit; }}
.stApp:has(.himshield-theme) [data-testid="stBaseButton-primary"] {{
  background: {TEAL}; border-color: {TEAL}; border-radius: .6rem; min-height: 2.7rem;
  font-weight: 650;
}}
.stApp:has(.himshield-theme) [data-testid="stBaseButton-primary"]:hover {{
  background: {PRIMARY}; border-color: {PRIMARY};
}}
.stApp:has(.himshield-theme) [data-testid="stBaseButton-secondary"] {{
  border-color: {BORDER}; border-radius: .6rem; color: {PRIMARY}; min-height: 2.65rem;
}}
.stApp:has(.himshield-theme) :is(a, button, input, [role="combobox"], summary):focus-visible {{
  outline: 2px solid {TEAL}; outline-offset: 3px;
}}
.stApp:has(.himshield-theme) [data-testid="stRadio"] label:has(input[type="radio"]) {{
  border: 1px solid {BORDER}; border-radius: .6rem; background: {SURFACE};
  padding: .45rem .65rem; margin: .15rem 0;
}}
.stApp:has(.himshield-theme) [data-testid="stRadio"] label:has(input:checked) {{
  background: #EAF4F5; border-color: {TEAL};
}}
.stApp:has(.himshield-theme) [data-testid="stSelectbox"] [role="combobox"] {{ color: {PRIMARY}; }}
.stApp:has(.himshield-theme) [data-testid="stWidgetLabel"] p {{ font-weight: 550; }}
.stApp:has(.himshield-theme) [data-testid="stForm"] {{
  border-color: {BORDER}; border-radius: .9rem; background: {BACKGROUND}; padding: 1.25rem;
}}
.stApp:has(.himshield-theme) [data-testid="stExpander"] details {{
  border: 1px solid {BORDER}; border-radius: .65rem; background: {SURFACE};
}}
.stApp:has(.himshield-theme) [data-testid="stExpander"] summary {{ color: {PRIMARY}; }}
.stApp:has(.himshield-theme) [role="tab"] {{ color: {SECONDARY}; }}
.stApp:has(.himshield-theme) [role="tab"][aria-selected="true"] {{ color: {TEAL}; font-weight: 650; }}
.stApp:has(.himshield-theme) [data-testid="stAlert"] {{ border-radius: .65rem; }}
.stApp:has(.himshield-theme) [data-testid="stImage"] img {{ border-radius: .45rem; }}
.stApp:has(.himshield-theme) iframe {{ border: 1px solid {BORDER}; border-radius: .65rem; }}
.himshield-badges {{ display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .25rem; }}
.himshield-badge {{
  border: 1px solid {BORDER}; border-radius: 2rem; padding: .2rem .65rem;
  color: {SECONDARY}; background: {BACKGROUND}; font-size: .72rem; font-weight: 600;
}}
.himshield-wordmark {{ color: {PRIMARY}; font-size: 1.75rem; font-weight: 780; letter-spacing: -.05em; }}
.himshield-tagline {{ color: {SECONDARY}; font-size: .8rem; line-height: 1.65; margin-top: .4rem; }}
.himshield-brand {{ padding: .25rem 0 1.35rem; border-bottom: 1px solid {BORDER}; }}
.himshield-brand-heading {{ display: flex; align-items: center; gap: .65rem; }}
.himshield-brand-mark {{
  display: block; flex: 0 0 auto; width: 2.5rem; height: 2.5rem;
}}
.himshield-legend {{
  display: flex; flex-wrap: wrap; gap: .65rem 1.25rem; list-style: none;
  padding: .9rem 1rem; margin: .25rem 0 .5rem; border: 1px solid {BORDER};
  border-radius: .65rem; background: {BACKGROUND}; color: {TEXT}; font-size: .8rem;
}}
.himshield-legend li {{ display: flex; align-items: center; gap: .5rem; }}
.himshield-swatch {{ flex: 0 0 .8rem; height: .8rem; border: 1px solid {SECONDARY}; border-radius: .2rem; }}
.st-key-himshield-overview-stats {{ container: himshield-stats / inline-size; }}
.st-key-himshield-panel-overview-benchmark {{ container: himshield-benchmark / inline-size; }}
.st-key-himshield-overview-links {{ container: himshield-links / inline-size; }}
:is(.st-key-himshield-overview-stats, .st-key-himshield-panel-overview-benchmark,
    .st-key-himshield-overview-links) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem;
}}
:is(.st-key-himshield-overview-stats, .st-key-himshield-panel-overview-benchmark,
    .st-key-himshield-overview-links) > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
  width: auto; min-width: 0;
}}
.st-key-himshield-panel-overview-benchmark > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
  grid-template-columns: repeat(3, minmax(0, 1fr));
}}
.st-key-himshield-overview-links > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
}}
[class*="st-key-himshield-panel-"] [data-testid="stPageLink-NavLink"] {{
  max-width: 100%; height: auto; align-items: flex-start;
}}
[class*="st-key-himshield-panel-"] [data-testid="stPageLink-NavLink"] p {{
  white-space: normal; overflow-wrap: anywhere;
}}
.st-key-himshield-panel-overview-explore {{ border-top: 3px solid {TEAL}; }}
.himshield-coverage-title {{
  color: {PRIMARY}; font-size: 1.8rem; font-weight: 750; letter-spacing: -.035em; line-height: 1.2;
  margin: .2rem 0 .75rem;
}}
.himshield-coverage-secondary {{
  border-left: 2px solid {BORDER}; padding: .1rem 0 .1rem .85rem; color: {SECONDARY};
  font-size: .85rem; line-height: 1.6;
}}
.himshield-coverage-secondary strong {{ color: {PRIMARY}; font-weight: 650; }}
.himshield-coverage-secondary p {{ margin: .2rem 0 0; }}
.st-key-himshield-explorer-cta [data-testid="stPageLink-NavLink"] {{
  border: 1px solid {TEAL}; border-radius: .6rem; background: {TEAL};
  color: {SURFACE}; padding: .75rem 1rem; justify-content: center;
}}
.st-key-himshield-explorer-cta [data-testid="stPageLink-NavLink"] :is(p, [data-testid="stIconMaterial"]) {{
  color: {SURFACE}; font-weight: 600;
}}
.st-key-himshield-explorer-cta [data-testid="stPageLink-NavLink"]:hover {{
  background: {PRIMARY}; border-color: {PRIMARY};
}}
@container himshield-stats (max-width: 760px) {{
  .st-key-himshield-overview-stats > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}
}}
@container himshield-stats (max-width: 400px) {{
  .st-key-himshield-overview-stats > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
    grid-template-columns: minmax(0, 1fr);
  }}
}}
@container himshield-benchmark (max-width: 560px) {{
  .st-key-himshield-panel-overview-benchmark > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
    grid-template-columns: minmax(0, 1fr);
  }}
}}
@container himshield-links (max-width: 760px) {{
  .st-key-himshield-overview-links > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {{
    grid-template-columns: minmax(0, 1fr);
  }}
}}
@media (min-width: 641px) and (max-width: 1150px) {{
  [class*="st-key-himshield-panel-"] {{ padding: 1rem; }}
}}
@media (max-width: 640px) {{
  .stApp:has(.himshield-theme) [data-testid="stMainBlockContainer"] {{ padding: 2.75rem 1rem; }}
  .st-key-himshield-header {{ padding: 1.15rem; border-radius: .75rem; }}
  .st-key-himshield-header h1 {{ font-size: 1.9rem; overflow-wrap: anywhere; }}
  [class*="st-key-himshield-panel-"] {{ padding: 1rem; }}
  .stApp:has(.himshield-theme) [data-testid="stForm"] {{ padding: .75rem; }}
  .himshield-legend {{ gap: .65rem; padding: .75rem; }}
}}
</style>
<span class="himshield-theme" aria-hidden="true"></span>
"""


def install() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, description: str) -> None:
    with st.container(key="himshield-header"):
        st.title(title)
        st.markdown(description)


def panel(key: str, *, model: str | None = None):
    """A native container with an owned, stable styling class."""
    tone = "-tone-" + MODEL_ACCENTS[model][0] if model in MODEL_ACCENTS else ""
    return st.container(border=False, key="himshield-panel-" + key + tone)


def metric_card(column, key: str, label: str, value: str, *, help: str | None = None,
                model: str | None = None) -> None:
    with column:
        with panel("metric-" + key, model=model):
            st.caption(label, help=help)
            st.metric(label, value, help=help, label_visibility="collapsed")


def caption(text: str) -> None:
    st.caption(text)


def availability(title: str, detail: str, *, warning: bool = False) -> None:
    """Retain native, accessible status messages without suggesting automatic rebuilds."""
    message = f"**{title}** {detail}"
    if warning:
        st.warning(message)
    else:
        st.info(message)


def sidebar_brand() -> None:
    mark = Path(__file__).resolve().parent / "assets" / "himshield-mark.svg"
    encoded_mark = b64encode(mark.read_bytes()).decode("ascii")
    st.markdown(
        '<div class="himshield-brand"><div class="himshield-brand-heading">'
        f'<img class="himshield-brand-mark" src="data:image/svg+xml;base64,{encoded_mark}" '
        'alt="HimShield mountain and shield emblem" width="40" height="40" />'
        '<div class="himshield-wordmark">HimShield</div></div>'
        '<div class="himshield-tagline">Landslide susceptibility analytics</div></div>',
        unsafe_allow_html=True,
    )


def model_availability(paths: dict) -> None:
    # File availability, not a claim that a model has been deserialized or validated.
    for name, path in paths.items():
        state = "file available" if path.is_file() else "file unavailable"
        st.caption(f"{name}: {state}")


def figure(path, caption: str | None = None) -> None:
    if path.is_file():
        st.image(str(path), caption=caption)
    else:
        availability("Figure unavailable.", "The saved figure is missing. No scientific output is regenerated here.")


def susceptibility_legend(names, breaks, colours) -> None:
    """Text and ranges accompany the existing scientific colours, including boundary equality."""
    edges = [0.0, *breaks, 1.0]
    items = []
    for i, (name, colour) in enumerate(zip(names, colours)):
        interval = f"{edges[i]:.1f} ≤ score {'≤' if i == len(names) - 1 else '<'} {edges[i + 1]:.1f}"
        items.append(f'<li><span class="himshield-swatch" style="background:{escape(colour, quote=True)}" '
                     f'aria-hidden="true"></span><span>{escape(name)} · {escape(interval)}</span></li>')
    st.markdown('<ul class="himshield-legend" aria-label="Susceptibility classes">'
                + ''.join(items) + '</ul>', unsafe_allow_html=True)
