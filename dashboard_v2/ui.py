"""Presentation components used only by the HimShield dashboard.

No shared Streamlit settings, model inputs or saved artifacts are changed here.
Containers use Streamlit's documented key classes rather than generated CSS names.
"""
import streamlit as st

NAVY = "#102A43"
TEAL = "#0F766E"
BACKGROUND = "#F5F7FA"
SURFACE = "#FFFFFF"
TEXT = "#172B4D"
SECONDARY = "#526579"
BORDER = "#D8E2EC"

BENCHMARK_NOTE = (
    "Original random held-out benchmark. Spatial-validation infrastructure exists; "
    "performance results are pending."
)
THRESHOLD_NOTE = (
    "Youden thresholds were selected on the held-out test set. They are retrospective benchmark "
    "thresholds, not independently validated deployment thresholds."
)
SCORE_NOTE = (
    "Susceptibility scores rank model outputs; they are not calibrated probabilities of a landslide "
    "occurring. Low susceptibility does not guarantee safety."
)

# :has gates even the application background to this dashboard's own marker.
# Other selectors address owned key classes or semantic headings. No Emotion
# class names, nth-child selectors, widget internals or shared theme mutation.
CSS = f"""
<style>
.stApp:has(.himshield-theme) {{
  background: {BACKGROUND}; color: {TEXT};
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}}
.st-key-himshield-header {{
  border-bottom: 2px solid {TEAL}; padding-bottom: 1rem; margin-bottom: .5rem;
}}
.st-key-himshield-header h1 {{
  color: {NAVY}; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: clamp(1.8rem, 3vw, 2.6rem); line-height: 1.2; letter-spacing: -.025em;
}}
.st-key-himshield-header p {{ color: {SECONDARY}; line-height: 1.6; }}
[class*="st-key-himshield-panel-"] {{
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: .65rem;
  padding: 1rem; color: {TEXT};
}}
[class*="st-key-himshield-panel-"] h2,
[class*="st-key-himshield-panel-"] h3 {{ color: {NAVY}; }}
[class*="st-key-himshield-panel-metric-"] {{
  border-top: 3px solid {TEAL}; font-variant-numeric: tabular-nums;
}}
.himshield-eyebrow {{
  color: {TEAL}; font-size: .8rem; font-weight: 650; letter-spacing: .04em;
}}
.himshield-wordmark {{ color: {NAVY}; font-size: 1.65rem; font-weight: 750; }}
.himshield-tagline {{ color: {SECONDARY}; font-size: .9rem; line-height: 1.5; }}
.himshield-brand {{ border-left: 3px solid {TEAL}; padding-left: .8rem; margin-bottom: 1rem; }}
@media (max-width: 640px) {{
  [class*="st-key-himshield-panel-"] {{ padding: .75rem; }}
  .st-key-himshield-header h1 {{ font-size: 1.8rem; }}
}}
</style>
<span class="himshield-theme" aria-hidden="true"></span>
"""


def install() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, description: str) -> None:
    with st.container(key="himshield-header"):
        st.markdown('<div class="himshield-eyebrow">HimShield · Uttarakhand</div>', unsafe_allow_html=True)
        st.title(title)
        st.markdown(description)
        st.caption(BENCHMARK_NOTE)


def panel(key: str):
    """A native container with an owned, stable styling class."""
    return st.container(border=False, key="himshield-panel-" + key)


def metric_card(column, key: str, label: str, value: str, *, help: str | None = None) -> None:
    with column:
        with panel("metric-" + key):
            st.metric(label, value, help=help)


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
    st.markdown(
        '<div class="himshield-brand"><div class="himshield-wordmark">HimShield</div>'
        '<div class="himshield-tagline">Landslide susceptibility analytics<br>Uttarakhand, India</div></div>',
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
