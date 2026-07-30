"""
AI Creative Studio - Streamlit Frontend
Run: streamlit run app.py
"""
import io
import os
import requests
import streamlit as st
from PIL import Image
from streamlit_option_menu import option_menu

BACKEND = "http://localhost:8765"

st.set_page_config(
    page_title="AI Creative Studio",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
#MainMenu, footer, header { visibility: hidden; }

[data-testid="stSidebarCollapseButton"] { display: none !important; }
[data-testid="collapsedControl"]        { display: none !important; }
button[kind="header"]                   { display: none !important; }

[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e8eaf0 !important;
    box-shadow: 2px 0 12px rgba(0,0,0,.06) !important;
}
[data-testid="stSidebar"] > div:first-child { background:#ffffff !important; padding:0 !important; }

[data-testid="stAppViewContainer"] { background: #f5f6fa !important; }
[data-testid="stMain"]             { background: #f5f6fa !important; }
.main .block-container { background:#f5f6fa !important; padding:2rem 2.5rem !important; max-width:1120px !important; }

.sidebar-logo { padding:22px 18px 14px; font-size:17px; font-weight:700; color:#4f46e5; border-bottom:1px solid #eef0f6; display:flex; align-items:center; gap:8px; }
.nav-section-label { padding:14px 18px 5px; font-size:10px; font-weight:700; letter-spacing:1.4px; text-transform:uppercase; color:#9ca3c0; }
.nav-badge { background:#eef0ff; color:#6366f1; border-radius:20px; font-size:10px; padding:1px 7px; font-weight:700; }
.nav-divider { border:none; border-top:1px solid #eef0f6; margin:6px 10px; }

.tool-title { font-size:25px; font-weight:700; color:#1a1a2e; margin-bottom:4px; margin-top:0; }
.tool-sub   { font-size:14px; color:#6b7280; margin-bottom:20px; }
.model-badge { display:inline-block; background:#eef0ff; color:#4f46e5; border-radius:20px; font-size:12px; font-weight:600; padding:3px 12px; margin-bottom:14px; }

.gen-btn > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important; width: 100% !important;
    padding: 12px 0 !important; font-size: 15px !important;
    font-weight: 600 !important; margin-top: 10px !important;
    box-shadow: 0 4px 14px rgba(99,102,241,.25) !important;
}
.gen-btn > button:hover { box-shadow: 0 6px 22px rgba(99,102,241,.45) !important; transform:translateY(-1px) !important; }

.status-box { margin:10px 14px 16px; padding:8px 13px; border-radius:8px; font-size:12px; font-weight:600; }
.status-ok  { background:#f0fdf4; color:#16a34a; border:1px solid #bbf7d0; }
.status-off { background:#fff1f2; color:#e11d48; border:1px solid #fecdd3; }
</style>
""", unsafe_allow_html=True)


# -- Helpers -------------------------------------------------------------------
def call_api(endpoint, data=None, files=None):
    try:
        resp = requests.post(f"{BACKEND}{endpoint}", data=data or {}, files=files, timeout=300)
        if resp.status_code == 200:
            return resp.content
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        st.error(f"**Error:** {detail}")
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach backend. Run: `uvicorn backend.main:app --port 8765 --reload`")
    except Exception as e:
        st.error(f"Request failed: {e}")
    return None


def show_image(img_bytes, caption="Result", key="dl"):
    img = Image.open(io.BytesIO(img_bytes))
    st.image(img_bytes, caption=f"{caption}  ({img.width}x{img.height}px)", width="stretch")
    st.download_button("Download PNG", data=img_bytes, file_name="result.png", mime="image/png", key=key)


def show_video(vid_bytes, mime="image/gif", key="dl_v"):
    if "gif" in mime:
        st.image(vid_bytes, width="stretch")
    else:
        st.video(vid_bytes)
    ext = "gif" if "gif" in mime else "mp4"
    st.download_button(f"Download {ext.upper()}", data=vid_bytes, file_name=f"result.{ext}", mime=mime, key=key)


def header(icon, title, subtitle, model_badge=None):
    st.markdown(f"<p class='tool-title'>{icon} {title}</p>", unsafe_allow_html=True)
    st.markdown(f"<p class='tool-sub'>{subtitle}</p>", unsafe_allow_html=True)
    if model_badge:
        st.markdown(f"<span class='model-badge'>&#9889; {model_badge}</span>", unsafe_allow_html=True)


def go_btn(label, key):
    st.markdown('<div class="gen-btn">', unsafe_allow_html=True)
    clicked = st.button(label, key=key, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)
    return clicked


# -- Sidebar -------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-logo">&#127912; AI Creative Studio</div>', unsafe_allow_html=True)

    st.markdown('<div class="nav-section-label">&#128444; IMAGE TOOLS <span class="nav-badge">8</span></div>', unsafe_allow_html=True)
    img_sel = option_menu(None,
        ["Text to Image","Image to Image","Product Shot","Face Swap","Outfit Swap","Remove Background","Upscale","Headshot"],
        icons=["image","palette","box-seam","emoji-smile","bag","scissors","arrow-up-circle","person-circle"],
        default_index=0, key="img_menu",
        styles={
            "container":{"padding":"0","background":"#ffffff"},
            "icon":{"color":"#6366f1","font-size":"14px"},
            "nav-link":{"font-size":"13.5px","color":"#4b5563","padding":"8px 16px","border-radius":"8px","margin":"1px 6px"},
            "nav-link-selected":{"background-color":"#eef0ff","color":"#4f46e5","font-weight":"600","border-left":"3px solid #6366f1"},
        })

    st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
    st.markdown('<div class="nav-section-label">&#127916; VIDEO TOOLS <span class="nav-badge">5</span></div>', unsafe_allow_html=True)
    vid_sel = option_menu(None,
        ["Text to Video","Image to Video","Video Clips","Motion Control","Lip Sync"],
        icons=["film","play-circle","scissors","joystick","mic"],
        default_index=0, key="vid_menu",
        styles={
            "container":{"padding":"0","background":"#ffffff"},
            "icon":{"color":"#7c3aed","font-size":"14px"},
            "nav-link":{"font-size":"13.5px","color":"#4b5563","padding":"8px 16px","border-radius":"8px","margin":"1px 6px"},
            "nav-link-selected":{"background-color":"#f3f0ff","color":"#6d28d9","font-weight":"600","border-left":"3px solid #7c3aed"},
        })

    st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
    st.markdown('<div class="nav-section-label">&#128197; BULK &amp; AUTOMATION <span class="nav-badge">2</span></div>', unsafe_allow_html=True)
    auto_sel = option_menu(None,
        ["Bulk Schedule via AI", "Smart Scheduling via AI"],
        icons=["calendar-range", "clock-history"],
        default_index=0, key="auto_menu",
        styles={
            "container":{"padding":"0","background":"#ffffff"},
            "icon":{"color":"#0891b2","font-size":"14px"},
            "nav-link":{"font-size":"13.5px","color":"#4b5563","padding":"8px 16px","border-radius":"8px","margin":"1px 6px"},
            "nav-link-selected":{"background-color":"#e0f2fe","color":"#0369a1","font-weight":"600","border-left":"3px solid #0891b2"},
        })

    st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
    st.markdown('<div class="nav-section-label">&#128221; CONTENT <span class="nav-badge">3</span></div>', unsafe_allow_html=True)
    content_sel = option_menu(None,
        ["Caption + Image", "Caption Generator", "Hashtag Generator"],
        icons=["file-image", "pencil-square", "hash"],
        default_index=0, key="content_menu",
        styles={
            "container":{"padding":"0","background":"#ffffff"},
            "icon":{"color":"#db2777","font-size":"14px"},
            "nav-link":{"font-size":"13.5px","color":"#4b5563","padding":"8px 16px","border-radius":"8px","margin":"1px 6px"},
            "nav-link-selected":{"background-color":"#fce7f3","color":"#be185d","font-weight":"600","border-left":"3px solid #db2777"},
        })

    st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
    st.markdown('<div class="nav-section-label">&#128269; RESEARCH <span class="nav-badge">1</span></div>', unsafe_allow_html=True)
    # Plain button — avoids option_menu's broken single-item change detection
    _ci_active = st.session_state.get("last_group","") == "research"
    _ci_style  = "background:#d1fae5;color:#065f46;border:1.5px solid #059669;border-radius:8px;padding:8px 16px;font-size:13.5px;font-weight:600;width:100%;text-align:left;cursor:pointer;"
    _ci_plain  = "background:#ffffff;color:#4b5563;border:none;border-radius:8px;padding:8px 16px;font-size:13.5px;width:100%;text-align:left;cursor:pointer;"
    if st.button("&#127970; Company Intelligence", key="ci_nav_btn",
                 use_container_width=True,
                 type="primary" if _ci_active else "secondary"):
        st.session_state.last_group = "research"
        st.rerun()
    research_sel = "Company Intelligence"  # always, used by routing below

    st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)
    try:
        ok = requests.get(f"{BACKEND}/health", timeout=2).status_code == 200
    except Exception:
        ok = False
    if ok:
        st.markdown('<div class="status-box status-ok">&#128994; Backend connected</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-box status-off">&#128308; Backend offline — run start_backend.bat</div>', unsafe_allow_html=True)


# -- Session state & routing ---------------------------------------------------
for k, d in [("last_group","image"),("prev_img",img_sel),("prev_vid",vid_sel),
              ("prev_auto",auto_sel),("prev_content",content_sel)]:
    if k not in st.session_state: st.session_state[k] = d

# Detect which option_menu changed (these all have multiple items so change-detection works)
if img_sel != st.session_state.prev_img:
    st.session_state.last_group = "image"; st.session_state.prev_img = img_sel
elif vid_sel != st.session_state.prev_vid:
    st.session_state.last_group = "video"; st.session_state.prev_vid = vid_sel
elif auto_sel != st.session_state.prev_auto:
    st.session_state.last_group = "auto"; st.session_state.prev_auto = auto_sel
elif content_sel != st.session_state.prev_content:
    st.session_state.last_group = "content"; st.session_state.prev_content = content_sel
# research is set directly by the sidebar button → st.session_state.last_group = "research"

# Resolve active tool
if st.session_state.last_group == "research":
    tool = "Company Intelligence"
elif st.session_state.last_group == "image":
    tool = img_sel
elif st.session_state.last_group == "video":
    tool = vid_sel
elif st.session_state.last_group == "auto":
    tool = auto_sel
else:
    tool = content_sel

ASPECT_RATIOS = {
    "1:1  Square (1024x1024)":       (1024, 1024),
    "4:3  Landscape (1152x896)":     (1152, 896),
    "3:4  Portrait (896x1152)":      (896,  1152),
    "16:9 Cinematic (1344x768)":     (1344, 768),
    "9:16 Stories/TikTok (768x1344)":(768,  1344),
    "3:2  Wide (1216x832)":          (1216, 832),
}

STYLE_OPTIONS = {"Photo Realistic":"photo","Cinematic":"cinematic","Portrait":"portrait","Product":"product","Social Media":"social_media"}
PLATFORM_OPTIONS = ["None","Instagram","LinkedIn","Twitter/X","YouTube","TikTok","Pinterest"]
BG_OPTIONS = ["Pure White","Soft Gray","Cream","Midnight Black","Sky Blue","Warm Beige"]
HEADSHOT_STYLES = ["Corporate White","Studio Gray","Outdoor Bokeh","Dark Executive"]
MOTION_EFFECTS = {"Ken Burns Zoom In":"zoom_in","Ken Burns Zoom Out":"zoom_out","Pan Left to Right":"pan_lr","Pan Right to Left":"pan_rl","Camera Shake":"shake"}
CLIP_OPS = ["Trim Video","Add Text Overlay","Extract Frames as GIF"]


# ==============================================================================
#  IMAGE TOOLS
# ==============================================================================

if tool == "Text to Image":
    header("&#128444;", "Text to Image",
           "Professional HD image generation — Azure OpenAI enhanced, FLUX quality.",
           "FLUX.1 Schnell via Together AI (auto-fallback to Flux-Realism)")

    if not os.getenv("TOGETHER_API_KEY"):
        st.info("**Unlock Best Quality (Free):** Sign up at [together.ai](https://together.ai) → add `TOGETHER_API_KEY=your_key` to `.env` → restart backend.")

    col_l, col_r = st.columns([3, 2], gap="large")
    with col_l:
        prompt = st.text_area("Describe your image", height=120,
            placeholder="e.g. Lionel Messi celebrating a goal under floodlights | A luxury watch on marble | Sunset over Eiffel Tower")
        neg = st.text_input("Negative Prompt (optional)", placeholder="blurry, distorted, watermark, extra limbs...")
        r1, r2 = st.columns(2)
        style    = r1.selectbox("Style", list(STYLE_OPTIONS.keys()))
        platform = r2.selectbox("Platform", PLATFORM_OPTIONS)
    with col_r:
        aspect_key   = st.selectbox("Aspect Ratio", list(ASPECT_RATIOS.keys()))
        width, height = ASPECT_RATIOS[aspect_key]
        st.caption(f"Resolution: {width} x {height} px")
        st.success("Azure OpenAI enhanced | Natural sharpening")

    if go_btn("Generate Image", "t2i"):
        if not prompt.strip():
            st.warning("Please enter a prompt.")
        else:
            with st.spinner("Enhancing prompt -> Generating HD image..."):
                out = call_api("/api/text-to-image", {
                    "prompt": prompt, "negative_prompt": neg,
                    "width": width, "height": height,
                    "style": STYLE_OPTIONS.get(style, "photo"), "platform": platform,
                })
            if out: show_image(out, "Generated Image", "t2i_dl")

elif tool == "Image to Image":
    header("&#127912;", "Image to Image",
           "Transform your image — change background, style or content.",
           "Smart Auto Mode: rembg + InstructPix2Pix + FLUX Realism")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Source Image", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        prompt = st.text_area("What to change?", height=100,
            placeholder="beach sunset background  |  anime style  |  make him wear a suit  |  cyberpunk city")
        neg = st.text_input("Avoid in output (optional)", placeholder="blurry, ugly, distorted...")
        st.info("**Background keywords** (beach, forest, city...) -> subject preserved, new bg generated\n\n**Style keywords** (anime, cartoon, oil paint...) -> full style transfer")

    if go_btn("Transform Image", "i2i"):
        if not uploaded or not prompt.strip():
            st.warning("Upload an image and enter what to change.")
        else:
            with st.spinner("Analysing image -> Transforming..."):
                out = call_api("/api/image-to-image", {
                    "prompt": prompt, "negative_prompt": neg,
                }, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out:
                c1, c2 = st.columns(2)
                with c1: st.image(uploaded, caption="Original", width="stretch")
                with c2: show_image(out, "Transformed", "i2i_dl")

elif tool == "Product Shot":
    header("&#128247;", "Product Shot",
           "Professional product photography with clean backgrounds.",
           "rembg isnet + PIL Compositing")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Product Image", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        bg     = st.selectbox("Background", BG_OPTIONS)
        shadow = st.toggle("Drop Shadow", value=True)
        st.success("Background removed automatically | Professional shadow added")

    if go_btn("Generate Product Shot", "ps"):
        if not uploaded:
            st.warning("Please upload a product image.")
        else:
            with st.spinner("Removing background -> Compositing..."):
                out = call_api("/api/product-shot", {
                    "background_key": bg, "shadow": str(shadow),
                }, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out: show_image(out, "Product Shot", "ps_dl")

elif tool == "Face Swap":
    header("&#128247;", "Face Swap",
           "Swap faces with landmark alignment and color correction.",
           "InsightFace + Landmark Align + Poisson Blend")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        src = st.file_uploader("Source Face (face to use)", type=["png","jpg","jpeg"])
        if src: st.image(src, caption="Source Face", width="stretch")
    with col_r:
        tgt = st.file_uploader("Target Image (face to replace)", type=["png","jpg","jpeg"])
        if tgt: st.image(tgt, caption="Target", width="stretch")

    st.info("Tip: Use clear, frontal face photos for best results. Both images should have visible faces.")

    if go_btn("Swap Face", "fs"):
        if not src or not tgt:
            st.warning("Upload both source and target images.")
        else:
            with st.spinner("Detecting landmarks -> Aligning -> Blending..."):
                out = call_api("/api/face-swap", {}, files={
                    "source": (src.name, src.getvalue(), src.type),
                    "target": (tgt.name, tgt.getvalue(), tgt.type),
                })
            if out: show_image(out, "Face Swapped", "fs_dl")

elif tool == "Outfit Swap":
    header("&#128084;", "Outfit Swap",
           "Virtually try on any outfit using Azure Vision + FLUX Realism.",
           "Azure OpenAI Vision + FLUX Realism HD")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Person Image", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        outfit = st.text_area("Describe the outfit", height=120,
            placeholder="red fitted blazer with black trousers and white sneakers\n\nblue denim jacket with white t-shirt and joggers")
        st.info("AI reads the person's body, pose and appearance, then generates them wearing your described outfit.")

    if go_btn("Swap Outfit", "os"):
        if not uploaded or not outfit.strip():
            st.warning("Upload a person photo and describe the outfit.")
        else:
            with st.spinner("Vision reading person -> Generating outfit..."):
                out = call_api("/api/outfit-swap", {
                    "outfit_prompt": outfit,
                }, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out: show_image(out, "Outfit Result", "os_dl")

elif tool == "Remove Background":
    header("&#9986;", "Remove Background",
           "AI background removal — BiRefNet (best) with rembg fallback.",
           "BiRefNet via HuggingFace -> rembg isnet fallback")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Image", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        st.info("BiRefNet is state-of-the-art for hair, fine edges and transparent objects.\n\nOutput is a PNG with transparent background.")

    if go_btn("Remove Background", "bg"):
        if not uploaded:
            st.warning("Please upload an image.")
        else:
            with st.spinner("Removing background..."):
                out = call_api("/api/remove-background", {},
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out:
                c1, c2 = st.columns(2)
                with c1: st.image(uploaded, caption="Original", width="stretch")
                with c2: show_image(out, "Background Removed", "bg_dl")

elif tool == "Upscale":
    header("&#11014;", "Upscale Image",
           "Increase resolution with sharpening for crisp, detailed output.",
           "Lanczos 4x + UnsharpMask + Sharpness Enhancer")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Image", type=["png","jpg","jpeg","webp"])
        if uploaded:
            st.image(uploaded, caption="Input", width="stretch")
            img = Image.open(io.BytesIO(uploaded.getvalue()))
            st.caption(f"Input: {img.width}x{img.height}px -> Output: {img.width*4}x{img.height*4}px")
    with col_r:
        scale = st.radio("Upscale Factor", [4, 2], horizontal=True, captions=["4x (Recommended)", "2x (Faster)"])
        st.success(f"Output will be {scale}x larger with enhanced sharpness")

    if go_btn("Upscale Image", "up"):
        if not uploaded:
            st.warning("Please upload an image.")
        else:
            with st.spinner(f"Upscaling {scale}x + sharpening..."):
                out = call_api("/api/upscale", {"scale": scale},
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out: show_image(out, f"Upscaled {scale}x", "up_dl")

elif tool == "Headshot":
    header("&#128100;", "Professional Headshot",
           "Transform any photo into a clean professional headshot.",
           "rembg Human Seg + Studio Background")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Photo", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        style = st.selectbox("Background Style", HEADSHOT_STYLES)
        st.info("Person is detected and cut out, then placed on a professional studio background. Best with clear portraits.")

    if go_btn("Generate Headshot", "hs"):
        if not uploaded:
            st.warning("Please upload a photo.")
        else:
            with st.spinner("Detecting person -> Applying studio background..."):
                out = call_api("/api/headshot", {"style_key": style},
                    files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out:
                c1, c2 = st.columns(2)
                with c1: st.image(uploaded, caption="Original", width="stretch")
                with c2: show_image(out, "Headshot", "hs_dl")


# ==============================================================================
#  VIDEO TOOLS
# ==============================================================================

elif tool == "Text to Video":
    header("&#127916;", "Text to Video",
           "Generate a cinematic animated clip from your description.",
           "FLUX Realism + Ken Burns Motion -> Animated GIF")

    col_l, col_r = st.columns([3, 2], gap="large")
    with col_l:
        prompt = st.text_area("Describe your video scene", height=130,
            placeholder="A majestic eagle soaring over snow-capped mountains at sunrise\n\nA busy Tokyo street at night with neon lights reflecting on wet pavement")
    with col_r:
        st.info("A high-quality still frame is generated from your prompt, then animated with a cinematic Ken Burns effect.")
        st.success("Output: Animated GIF | Cinematic zoom motion | ~5-15 seconds")

    if go_btn("Generate Video", "t2v"):
        if not prompt.strip():
            st.warning("Please describe your video scene.")
        else:
            with st.spinner("Generating cinematic frame -> Animating..."):
                out = call_api("/api/text-to-video", {"prompt": prompt})
            if out: show_video(out, "image/gif", "t2v_dl")

elif tool == "Image to Video":
    header("&#127916;", "Image to Video",
           "Animate a still image with smooth cinematic motion.",
           "PIL Frame Animation — Local, Instant")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Image", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        motion = st.selectbox("Motion Type", list(MOTION_EFFECTS.keys()))
        c1, c2 = st.columns(2)
        fps    = c1.slider("FPS", 6, 24, 12)
        frames = c2.slider("Frames", 12, 60, 30)
        st.info(f"Output: {frames} frames at {fps} fps = ~{frames/fps:.1f}s animated GIF")

    if go_btn("Animate Image", "i2v"):
        if not uploaded:
            st.warning("Please upload an image.")
        else:
            with st.spinner("Generating animation..."):
                out = call_api("/api/image-to-video", {
                    "motion": MOTION_EFFECTS[motion],
                    "num_frames": frames, "fps": fps,
                }, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out: show_video(out, "image/gif", "i2v_dl")

elif tool == "Video Clips":
    header("&#9986;", "Video Clips",
           "Trim, add text overlay or extract frames from a video.",
           "MoviePy — Local Processing")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Video", type=["mp4","mov","avi"])
    with col_r:
        op = st.selectbox("Operation", CLIP_OPS)
        if op == "Trim Video":
            c1, c2 = st.columns(2)
            start = c1.number_input("Start (s)", min_value=0.0, value=0.0, step=0.5)
            end   = c2.number_input("End (s)",   min_value=0.5, value=5.0, step=0.5)
            text_overlay = ""
            fps_val = 5
        elif op == "Add Text Overlay":
            text_overlay = st.text_input("Text to overlay", placeholder="My Brand Name")
            start, end, fps_val = 0, 0, 5
        else:
            fps_val = st.slider("GIF FPS", 3, 12, 5)
            start, end, text_overlay = 0, 0, ""

    if go_btn("Process Video", "vc"):
        if not uploaded:
            st.warning("Please upload a video.")
        else:
            with st.spinner("Processing video..."):
                out = call_api("/api/video-clips", {
                    "operation": op, "start_sec": start, "end_sec": end,
                    "text": text_overlay, "fps": fps_val,
                }, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out:
                mime = "image/gif" if op == "Extract Frames as GIF" else "video/mp4"
                show_video(out, mime, "vc_dl")

elif tool == "Motion Control":
    header("&#127918;", "Motion Control",
           "Apply camera motion effects to any image.",
           "PIL Cinematic Frame Animation — Local")

    col_l, col_r = st.columns([1, 1], gap="large")
    with col_l:
        uploaded = st.file_uploader("Upload Image", type=["png","jpg","jpeg","webp"])
        if uploaded: st.image(uploaded, caption="Input", width="stretch")
    with col_r:
        effect   = st.selectbox("Camera Motion", list(MOTION_EFFECTS.keys()))
        c1, c2   = st.columns(2)
        fps      = c1.slider("FPS", 8, 24, 15)
        duration = c2.slider("Duration (s)", 1, 6, 3)
        st.info(f"Output: {fps * duration} frames at {fps} fps = {duration}s animated GIF")

    if go_btn("Apply Motion Effect", "mc"):
        if not uploaded:
            st.warning("Please upload an image.")
        else:
            with st.spinner("Rendering animation..."):
                out = call_api("/api/motion-control", {
                    "effect_key": effect, "fps": fps, "duration_sec": duration,
                }, files={"file": (uploaded.name, uploaded.getvalue(), uploaded.type)})
            if out: show_video(out, "image/gif", "mc_dl")

elif tool == "Lip Sync":
    header("&#127908;", "Lip Sync",
           "Sync lip movements in a video to an audio track — no local setup needed.",
           "LatentSync via HF Spaces -> SadTalker -> Audio Replace fallback")

    st.info(
        "Upload a face video and an audio file. "
        "LatentSync (state-of-the-art) runs on HuggingFace Spaces for free — no installation required. "
        "If the Space is busy, SadTalker or audio replacement will be used automatically."
    )

    col_l, col_r = st.columns(2)
    with col_l:
        vid = st.file_uploader("Face Video", type=["mp4","mov"])
        if vid:
            st.video(vid)
    with col_r:
        aud = st.file_uploader("Audio File", type=["mp3","wav"])
        if aud:
            st.audio(aud)

    st.caption("Tip: Use a short video (5-15 seconds) for best results and faster processing.")

    if go_btn("Sync Lips", "ls"):
        if not vid or not aud:
            st.warning("Upload both a face video and an audio file.")
        else:
            with st.spinner("Connecting to LatentSync -> Syncing lips to audio... (may take 30-60s)"):
                out = call_api("/api/lip-sync", {}, files={
                    "video": (vid.name, vid.getvalue(), vid.type),
                    "audio": (aud.name, aud.getvalue(), aud.type),
                })
            if out: show_video(out, "video/mp4", "ls_dl")


# ==============================================================================
#  BULK & AUTOMATION TOOLS
# ==============================================================================

elif tool == "Bulk Schedule via AI":
    import json as _json
    header("&#128197;", "Bulk Schedule via AI",
           "Generate a complete content calendar — 7 or 30 days across all your platforms.",
           "Azure OpenAI (primary LLM)")

    col_l, col_r = st.columns([2, 3], gap="large")
    with col_l:
        instructions = st.text_area(
            "Brand Instructions (optional)",
            height=120,
            placeholder="e.g. Promote our summer sale with 3 posts a week across Instagram and LinkedIn...",
        )
        all_platforms = ["Instagram", "Facebook", "LinkedIn", "TikTok", "X (Twitter)", "Pinterest", "YouTube"]
        sel_platforms = st.multiselect("Platforms", all_platforms,
                                       default=["Instagram", "Facebook"])
        time_range = st.radio("Time Range", ["Next 7 days", "Next 30 days"], horizontal=True)
        tone = st.selectbox("Tone", ["Friendly", "Professional", "Bold", "Playful", "Inspirational"])

        st.markdown(
            f"<div style='margin-top:8px;padding:10px 14px;background:#e0f2fe;"
            f"border-radius:8px;font-size:13px;color:#0369a1;'>"
            f"<b>Will generate:</b> "
            f"{'7' if '7' in time_range else '30'} days &#215; "
            f"{len(sel_platforms) or 1} platforms = "
            f"<b>{('7' if '7' in time_range else '30') * (len(sel_platforms) or 1)} posts</b></div>",
            unsafe_allow_html=True,
        )

    with col_r:
        st.markdown(
            "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
            "padding:24px;min-height:280px;text-align:center;color:#94a3b8;'>"
            "<div style='font-size:40px;margin-bottom:12px'>&#128197;</div>"
            "<div style='font-size:15px;font-weight:600'>Your post plan will appear here</div>"
            "<div style='font-size:13px;margin-top:6px'>Fill in the settings on the left, then hit Generate</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    if go_btn("&#10024; Generate &amp; Queue Posts", "bs_gen"):
        if not sel_platforms:
            st.warning("Please select at least one platform.")
        else:
            with st.spinner(f"Generating {time_range.lower()} content calendar across {', '.join(sel_platforms)}..."):
                raw = call_api("/api/bulk-schedule", {
                    "instructions": instructions,
                    "platforms": ",".join(sel_platforms),
                    "time_range": time_range,
                    "tone": tone,
                })
            if raw:
                try:
                    data = _json.loads(raw)
                    posts = data.get("schedule", [])
                    if posts:
                        st.success(f"Generated {len(posts)} posts for your content calendar!")

                        # Group by day for display
                        from collections import defaultdict
                        days_map = defaultdict(list)
                        for p in posts:
                            days_map[p.get("day", "?")].append(p)

                        # Color map for platforms
                        pc = {"Instagram":"#e1306c","Facebook":"#1877f2","LinkedIn":"#0a66c2",
                              "TikTok":"#010101","X (Twitter)":"#1da1f2","Pinterest":"#e60023",
                              "YouTube":"#ff0000"}

                        for day_num in sorted(days_map.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                            day_posts = days_map[day_num]
                            date_label = day_posts[0].get("date", f"Day {day_num}")
                            st.markdown(f"### &#128197; {date_label}")
                            for p in day_posts:
                                plat  = p.get("platform", "")
                                color = pc.get(plat, "#6366f1")
                                ptype = p.get("post_type", "Post")
                                ttime = p.get("time", "")
                                cap   = p.get("caption_preview", "")
                                tags  = p.get("hashtags", "")
                                idea  = p.get("image_idea", "")
                                st.markdown(
                                    f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:10px;"
                                    f"padding:14px 18px;margin:6px 0;border-left:4px solid {color};'>"
                                    f"<div style='display:flex;gap:10px;align-items:center;margin-bottom:8px;'>"
                                    f"<span style='background:{color};color:#fff;border-radius:6px;padding:2px 10px;"
                                    f"font-size:12px;font-weight:700;'>{plat}</span>"
                                    f"<span style='background:#f1f5f9;color:#475569;border-radius:6px;padding:2px 8px;"
                                    f"font-size:12px;'>{ptype}</span>"
                                    f"<span style='color:#94a3b8;font-size:12px;margin-left:auto;'>&#128336; {ttime}</span>"
                                    f"</div>"
                                    f"<div style='font-size:14px;color:#1e293b;margin-bottom:6px;'>{cap}</div>"
                                    f"<div style='font-size:12px;color:#6366f1;margin-bottom:4px;'>{tags}</div>"
                                    f"<div style='font-size:12px;color:#94a3b8;'>&#128444; {idea}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                    else:
                        st.warning("No posts generated. Try different settings.")
                except Exception as ex:
                    st.error(f"Could not parse schedule: {ex}")
                    st.text(raw.decode() if isinstance(raw, bytes) else str(raw))


elif tool == "Smart Scheduling via AI":
    import json as _json
    header("&#128336;", "Smart Scheduling via AI",
           "AI picks the best posting times per platform based on your audience and goals.",
           "Azure OpenAI — data-driven scheduling")

    col_l, col_r = st.columns([2, 3], gap="large")
    with col_l:
        instructions = st.text_area(
            "Audience / Context (optional)",
            height=100,
            placeholder="e.g. Fashion brand targeting 18-35 year-old women in the US, EST timezone...",
        )
        all_platforms = ["Instagram", "Facebook", "LinkedIn", "TikTok", "X (Twitter)", "Pinterest", "YouTube"]
        sel_platforms = st.multiselect("Platforms", all_platforms,
                                       default=["Instagram", "LinkedIn"])
        optimize_for = st.radio("Optimize For", ["Reach", "Engagement", "Clicks"], horizontal=True)

    with col_r:
        st.markdown(
            "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
            "padding:24px;min-height:200px;text-align:center;color:#94a3b8;'>"
            "<div style='font-size:40px;margin-bottom:12px'>&#128336;</div>"
            "<div style='font-size:15px;font-weight:600'>Your schedule will appear here</div>"
            "<div style='font-size:13px;margin-top:6px'>Fill in settings, then click Enable Smart Scheduling</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    if go_btn("&#10024; Enable Smart Scheduling", "ss_gen"):
        if not sel_platforms:
            st.warning("Please select at least one platform.")
        else:
            with st.spinner(f"Analyzing optimal times for {', '.join(sel_platforms)} to maximize {optimize_for}..."):
                raw = call_api("/api/smart-schedule", {
                    "platforms": ",".join(sel_platforms),
                    "optimize_for": optimize_for,
                    "instructions": instructions,
                })
            if raw:
                try:
                    data = _json.loads(raw)

                    # Strategy summary
                    summary = data.get("strategy_summary", "")
                    if summary:
                        st.info(f"**Strategy:** {summary}")

                    # Weekly schedule
                    weekly = data.get("weekly_schedule", {})
                    if weekly:
                        st.markdown("### &#128197; Weekly Posting Schedule")
                        days_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                        pc = {"Instagram":"#e1306c","Facebook":"#1877f2","LinkedIn":"#0a66c2",
                              "TikTok":"#010101","X (Twitter)":"#1da1f2","Pinterest":"#e60023","YouTube":"#ff0000"}

                        for day in days_order:
                            if day not in weekly: continue
                            posts_today = weekly[day]
                            if not posts_today: continue
                            st.markdown(f"**{day}**")
                            cols = st.columns(min(len(posts_today), 3))
                            for i, p in enumerate(posts_today):
                                plat  = p.get("platform","")
                                color = pc.get(plat,"#6366f1")
                                ptime = p.get("time","")
                                ptype = p.get("post_type","Post")
                                reason= p.get("reason","")
                                with cols[i % 3]:
                                    st.markdown(
                                        f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:10px;"
                                        f"padding:12px;border-top:3px solid {color};margin-bottom:8px;'>"
                                        f"<div style='font-size:12px;font-weight:700;color:{color};'>{plat}</div>"
                                        f"<div style='font-size:18px;font-weight:700;color:#1e293b;margin:4px 0;'>{ptime}</div>"
                                        f"<div style='font-size:11px;color:#64748b;background:#f8fafc;border-radius:4px;"
                                        f"padding:2px 6px;display:inline-block;margin-bottom:6px;'>{ptype}</div>"
                                        f"<div style='font-size:11px;color:#94a3b8;'>{reason}</div>"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )

                    # Platform insights
                    insights = data.get("platform_insights", {})
                    if insights:
                        st.markdown("### &#128200; Platform Insights")
                        for plat, info in insights.items():
                            with st.expander(f"{plat} Insights"):
                                st.markdown(f"**Best Days:** {info.get('best_days','')}")
                                st.markdown(f"**Peak Hours:** {info.get('peak_hours','')}")
                                st.markdown(f"**Tip:** {info.get('tip','')}")

                    # Optimization tips
                    tips = data.get("optimization_tips", [])
                    if tips:
                        st.markdown("### &#128161; Optimization Tips")
                        for tip in tips:
                            st.markdown(f"&#10003; {tip}")

                except Exception as ex:
                    st.error(f"Could not parse schedule: {ex}")
                    st.text(raw.decode() if isinstance(raw, bytes) else str(raw))


# ==============================================================================
#  CONTENT TOOLS  — Caption+Image / Caption Generator / Hashtag Generator
# ==============================================================================

elif tool == "Caption + Image":
    import base64 as _b64
    import json as _json
    header("&#128444;", "Caption + Image",
           "Generate a matching viral caption AND high-quality image together in one click.",
           "Azure OpenAI caption + FLUX.1 Schnell image")

    # ── session state ─────────────────────────────────────────────────────────
    if "ci_caption"  not in st.session_state: st.session_state.ci_caption  = ""
    if "ci_img_b64"  not in st.session_state: st.session_state.ci_img_b64  = ""
    if "ci_platform" not in st.session_state: st.session_state.ci_platform = ""
    if "ci_tone"     not in st.session_state: st.session_state.ci_tone     = ""
    if "ci_history"  not in st.session_state: st.session_state.ci_history  = []

    # ── settings panel ────────────────────────────────────────────────────────
    col_l, col_r = st.columns([2, 3], gap="large")
    with col_l:
        topic    = st.text_area("Describe your post idea", height=110,
                                placeholder="e.g. A motivational Monday post for a fitness studio...")
        tone     = st.radio("Tone", ["Friendly", "Bold", "Professional", "Playful", "Inspirational"])
        platform = st.selectbox("Platform",
                                ["Instagram", "LinkedIn", "Facebook", "TikTok",
                                 "X (Twitter)", "Pinterest", "YouTube"])
        st.markdown(
            "<div style='background:#fdf4ff;border:1px solid #e9d5ff;border-radius:8px;"
            "padding:9px 13px;font-size:12px;color:#7c3aed;'>"
            "&#128161; AI writes the caption AND generates a matching image in one pass!"
            "</div>", unsafe_allow_html=True)

        st.markdown('<div class="gen-btn">', unsafe_allow_html=True)
        do_ci = st.button("&#10024; Generate Post", key="ci_gen", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        if st.session_state.ci_caption == "" and st.session_state.ci_img_b64 == "":
            st.markdown(
                "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
                "padding:36px 24px;text-align:center;color:#94a3b8;margin-top:10px;'>"
                "<div style='font-size:44px;margin-bottom:14px'>&#128444;</div>"
                "<div style='font-size:15px;font-weight:600;color:#64748b;'>Your post will appear here</div>"
                "<div style='font-size:13px;margin-top:6px;'>Fill in the settings on the left, then Generate Post</div>"
                "</div>", unsafe_allow_html=True)

    # ── generate ─────────────────────────────────────────────────────────────
    if do_ci:
        if not topic.strip():
            st.warning("Please describe your post idea.")
        else:
            with st.spinner("Writing caption with Azure OpenAI... generating image with FLUX..."):
                raw = call_api("/api/caption-image", {
                    "topic": topic, "tone": tone, "platform": platform,
                })
            if raw:
                try:
                    result = _json.loads(raw)
                    st.session_state.ci_caption  = result.get("caption", "")
                    st.session_state.ci_img_b64  = result.get("image_b64", "")
                    st.session_state.ci_platform = platform
                    st.session_state.ci_tone     = tone
                    if st.session_state.ci_caption:
                        preview = st.session_state.ci_caption[:120] + (
                            "..." if len(st.session_state.ci_caption) > 120 else "")
                        st.session_state.ci_history.insert(0, {
                            "platform": platform, "tone": tone, "preview": preview,
                        })
                        st.session_state.ci_history = st.session_state.ci_history[:4]
                    st.rerun()
                except Exception as ex:
                    st.error(f"Could not parse result: {ex}")

    # ── results (inside Caption+Image block, shown after rerun) ───────────────
    ci_cap     = st.session_state.ci_caption
    ci_img_b64 = st.session_state.ci_img_b64

    if ci_cap or ci_img_b64:
        st.markdown("---")
        r1, r2 = st.columns([3, 2], gap="large")
        with r1:
            if ci_cap:
                st.markdown(
                    "<div style='background:#fdf4ff;border:2px solid #e9d5ff;border-radius:10px;"
                    "padding:6px 16px 2px;margin-bottom:6px;'>"
                    "<p style='font-size:11px;font-weight:700;letter-spacing:1px;color:#7c3aed;"
                    "text-transform:uppercase;margin:6px 0 4px;'>&#128221; Your Caption</p>"
                    "</div>", unsafe_allow_html=True)
                st.text_area("", value=ci_cap, height=180, key="ci_cap_disp")
                st.download_button("&#128203; Download Caption", data=ci_cap,
                                   file_name="caption.txt", mime="text/plain", key="ci_cap_dl")
        with r2:
            if ci_img_b64:
                try:
                    ib = _b64.b64decode(ci_img_b64)
                    st.image(ib, use_container_width=True,
                             caption=f"{st.session_state.ci_platform} | {st.session_state.ci_tone}")
                    st.download_button("&#11015; Download Image", data=ib,
                                       file_name="post_image.png", mime="image/png", key="ci_img_dl")
                except Exception as ex:
                    st.error(f"Image error: {ex}")

        hist = st.session_state.ci_history
        if len(hist) > 1:
            st.markdown("**&#128336; Recent Generations**")
            hc = st.columns(2)
            for i, h in enumerate(hist):
                pc = {"Instagram":"#e1306c","LinkedIn":"#0a66c2","Facebook":"#1877f2",
                      "TikTok":"#010101","X (Twitter)":"#1da1f2"}.get(h["platform"],"#6366f1")
                with hc[i % 2]:
                    st.markdown(
                        f"<div style='border-left:3px solid {pc};background:#f8fafc;"
                        f"border-radius:6px;padding:10px 14px;margin-bottom:8px;'>"
                        f"<b style='color:{pc};font-size:12px;'>{h['platform']}</b> "
                        f"<span style='color:#94a3b8;font-size:11px;'>{h['tone']}</span><br>"
                        f"<span style='font-size:13px;color:#374151;'>{h['preview']}</span>"
                        f"</div>", unsafe_allow_html=True)

elif tool == "Caption Generator":
    import json as _json
    header("&#9998;", "Caption Generator",
           "Write on-brand captions in seconds, tuned to your tone of voice.",
           "Azure OpenAI — primary writing model")

    if "cg_variants" not in st.session_state: st.session_state.cg_variants = []
    if "cg_history"  not in st.session_state: st.session_state.cg_history  = []

    col_l, col_r = st.columns([2, 3], gap="large")
    with col_l:
        cg_topic    = st.text_area("Describe the photo or post", height=110,
                                   placeholder="e.g. Behind the scenes at our bakery on a Monday morning...")
        cg_tone     = st.radio("Tone", ["Friendly", "Witty", "Professional", "Inspirational", "Bold"])
        cg_length   = st.radio("Length", ["Short", "Medium", "Long"], horizontal=True)
        cg_platform = st.selectbox("Platform",
                                   ["Instagram", "LinkedIn", "Twitter/X", "TikTok", "Facebook", "Pinterest"])
        st.markdown('<div class="gen-btn">', unsafe_allow_html=True)
        do_cg = st.button("&#10024; Generate Captions", key="cg_gen", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        cg_vars = st.session_state.cg_variants
        if cg_vars:
            st.success(f"{len(cg_vars)} caption options ready!")
            tabs = st.tabs([f"Option {i+1}" for i in range(len(cg_vars))])
            for i, (tab, cap) in enumerate(zip(tabs, cg_vars), 1):
                with tab:
                    st.text_area("Caption (select all to copy)", value=cap,
                                 height=160, key=f"cg_ta_{i}")
                    st.download_button(f"&#128203; Download Option {i}", data=cap,
                                       file_name=f"caption_{i}.txt", mime="text/plain",
                                       key=f"cg_dl_{i}")
            cg_hist = st.session_state.cg_history
            if len(cg_hist) > 1:
                st.markdown("---")
                st.markdown("**&#128336; Recent Generations**")
                hc2 = st.columns(2)
                for i, h in enumerate(cg_hist):
                    pc = {"Instagram":"#e1306c","LinkedIn":"#0a66c2","Twitter/X":"#1da1f2",
                          "TikTok":"#010101","Facebook":"#1877f2"}.get(h["platform"],"#6366f1")
                    with hc2[i % 2]:
                        st.markdown(
                            f"<div style='border-left:3px solid {pc};background:#f8fafc;"
                            f"border-radius:6px;padding:10px 14px;margin-bottom:8px;'>"
                            f"<b style='color:{pc};font-size:12px;'>{h['platform']}</b> "
                            f"<span style='color:#94a3b8;font-size:11px;'>{h['tone']}</span><br>"
                            f"<span style='font-size:13px;color:#374151;'>{h['preview']}</span>"
                            f"</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
                "padding:36px 24px;text-align:center;color:#94a3b8;margin-top:10px;'>"
                "<div style='font-size:44px;margin-bottom:14px'>&#9998;</div>"
                "<div style='font-size:15px;font-weight:600;color:#64748b;'>Your captions will appear here</div>"
                "<div style='font-size:13px;margin-top:6px;'>Fill in the settings on the left</div>"
                "</div>", unsafe_allow_html=True)

    if do_cg:
        if not cg_topic.strip():
            st.warning("Please describe your photo or post.")
        else:
            with st.spinner(f"Writing 3 {cg_tone.lower()} {cg_length.lower()} captions for {cg_platform}..."):
                raw = call_api("/api/caption-generator", {
                    "topic": cg_topic, "tone": cg_tone,
                    "length": cg_length, "platform": cg_platform,
                })
            if raw:
                try:
                    data = _json.loads(raw)
                    captions_text = data.get("captions", "")
                except Exception:
                    captions_text = raw.decode() if isinstance(raw, bytes) else str(raw)

                lines_t = captions_text.strip().split("\n")
                variants, current = [], []
                for line in lines_t:
                    s = line.strip()
                    if s and len(s) > 2 and s[0].isdigit() and s[1] == ".":
                        if current: variants.append("\n".join(current).strip())
                        current = [s[2:].strip()]
                    elif s:
                        current.append(s)
                if current: variants.append("\n".join(current).strip())
                if not variants: variants = [captions_text]

                st.session_state.cg_variants = variants[:3]
                if variants:
                    st.session_state.cg_history.insert(0, {
                        "platform": cg_platform, "tone": cg_tone,
                        "preview": variants[0][:90] + ("..." if len(variants[0]) > 90 else "")
                    })
                    st.session_state.cg_history = st.session_state.cg_history[:4]
                st.rerun()

elif tool == "Hashtag Generator":
    import json as _json
    header("&#35;", "Hashtag Generator",
           "Get relevant, high-reach hashtags tailored to each post and platform.",
           "Azure OpenAI — 30 hashtags in 3 tiers")

    if "hg_result" not in st.session_state: st.session_state.hg_result = ""

    col_l, col_r = st.columns([2, 3], gap="large")
    with col_l:
        hg_topic    = st.text_area("Paste your caption or describe your post", height=110,
                                   placeholder="e.g. Monday motivation post about gym fitness...")
        hg_platform = st.selectbox("Platform",
                                   ["Instagram", "TikTok", "Twitter/X", "LinkedIn",
                                    "Pinterest", "Facebook", "YouTube"])
        hg_reach    = st.radio("Reach Strategy", ["Niche", "Balanced", "Broad"], horizontal=True)
        st.markdown(
            "<div style='background:#fef3c7;border:1px solid #fde68a;border-radius:8px;"
            "padding:9px 13px;font-size:12px;color:#92400e;'>"
            "<b>Niche</b> = high engagement &bull; <b>Balanced</b> = best of both &bull; <b>Broad</b> = max reach"
            "</div>", unsafe_allow_html=True)
        st.markdown('<div class="gen-btn">', unsafe_allow_html=True)
        do_hg = st.button("&#10024; Generate Hashtags", key="hg_gen", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_r:
        hg_text = st.session_state.hg_result
        if hg_text:
            st.success("30 hashtags generated in 3 tiers!")
            sections = hg_text.split("###")
            for section in sections:
                section = section.strip()
                if not section: continue
                sec_lines = section.split("\n", 1)
                title = sec_lines[0].strip()
                body  = sec_lines[1].strip() if len(sec_lines) > 1 else ""
                if "Quick Copy" in title:
                    st.markdown("### &#128203; Quick Copy — All 30 Hashtags")
                    st.code(body.strip(), language=None)
                    st.download_button("&#11015; Download", data=body.strip(),
                                       file_name="hashtags.txt", mime="text/plain", key="ht_dl")
                else:
                    color = "#6366f1" if "Niche" in title else ("#f59e0b" if "Mid" in title else "#10b981")
                    tags  = [t.strip() for t in body.split() if t.strip().startswith("#")]
                    if tags:
                        tag_html = "".join(
                            f"<span style='background:{color}18;color:{color};border-radius:20px;"
                            f"padding:4px 12px;font-size:13px;font-weight:600;"
                            f"margin:3px 3px 3px 0;display:inline-block;'>{t}</span>"
                            for t in tags)
                        st.markdown(
                            f"<div style='margin-bottom:18px;'>"
                            f"<div style='font-size:12px;font-weight:700;color:{color};"
                            f"text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;'>"
                            f"&#9632; {title}</div><div>{tag_html}</div></div>",
                            unsafe_allow_html=True)
        else:
            st.markdown(
                "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
                "padding:36px 24px;text-align:center;color:#94a3b8;margin-top:10px;'>"
                "<div style='font-size:44px;margin-bottom:14px'>&#35;</div>"
                "<div style='font-size:15px;font-weight:600;color:#64748b;'>Your hashtag set will appear here</div>"
                "<div style='font-size:13px;margin-top:6px;'>Fill in the settings on the left</div>"
                "</div>", unsafe_allow_html=True)

    if do_hg:
        if not hg_topic.strip():
            st.warning("Please describe your post or paste your caption.")
        else:
            with st.spinner(f"Finding best {hg_reach.lower()} hashtags for {hg_platform}..."):
                raw = call_api("/api/hashtag-generator", {
                    "topic": hg_topic, "platform": hg_platform, "reach": hg_reach,
                })
            if raw:
                try:
                    data = _json.loads(raw)
                    hashtag_text = data.get("hashtags", "")
                except Exception:
                    hashtag_text = raw.decode() if isinstance(raw, bytes) else str(raw)
                st.session_state.hg_result = hashtag_text
                st.rerun()

# =============================================================================
# COMPANY INTELLIGENCE  — URL in → full deep report out
# =============================================================================
elif tool == "Company Intelligence":
    from urllib.parse import urlparse

    def _has_data(v):
        """Return True only if value is real confirmed data."""
        if not v:
            return False
        s = str(v).strip().lower()
        return s not in ("", "n/a", "na", "none", "null", "unknown") and \
               "not publicly" not in s and "not available" not in s and \
               "not found" not in s and "no data" not in s

    def _val(field):
        """Extract value from {value, source, confidence} dict or plain string."""
        if isinstance(field, dict):
            return field.get("value", "")
        return str(field) if field else ""

    def _cite(field):
        """Return HTML citation + confidence badge for a field dict."""
        if not isinstance(field, dict):
            return ""
        src  = field.get("source", "")
        conf = field.get("confidence", "")
        conf_color = {"High": "#16a34a", "Medium": "#d97706", "Low": "#dc2626"}.get(conf, "#64748b")
        src_icons  = {
            "ZaubaCorp": "&#9989;", "MCA": "&#9989;",
            "Website": "&#127760;", "Homepage scan": "&#127760;",
            "Glassdoor search": "&#11088;", "AmbitionBox search": "&#11088;",
            "Search": "&#128269;", "DuckDuckGo": "&#128269;",
        }
        icon = next((v for k, v in src_icons.items() if k.lower() in src.lower()), "&#128209;")
        html = ""
        if src:
            html += (f"<span style='font-size:10px;background:#f1f5f9;color:#475569;"
                     f"border-radius:4px;padding:1px 5px;margin-left:6px;'>"
                     f"{icon} {src}</span>")
        if conf:
            html += (f"<span style='font-size:10px;background:#f8fafc;color:{conf_color};"
                     f"border-radius:4px;padding:1px 5px;margin-left:3px;font-weight:700;'>"
                     f"&#9679; {conf}</span>")
        return html

    def _row(label, field):
        """Render one labelled row with value + citation badge."""
        v = _val(field)
        if not _has_data(v):
            return
        st.markdown(
            f"<div style='padding:5px 0;border-bottom:1px solid #f1f5f9;'>"
            f"<span style='color:#64748b;font-size:12px;font-weight:600;'>{label}:</span>&nbsp;"
            f"<span style='color:#1e293b;font-size:13px;'>{v}</span>"
            f"{_cite(field)}</div>",
            unsafe_allow_html=True)

    header("&#128269;", "Company Intelligence",
           "Paste any company URL — get a full competitive intelligence report instantly")

    # ── Input ──────────────────────────────────────────────────────────────
    ci_url = st.text_input("", placeholder="https://www.tesla.com  or  tesla.com",
                           label_visibility="collapsed")
    run_ci = st.button("&#128269;  Analyse Company", type="primary", use_container_width=True)

    if run_ci:
        if not ci_url.strip():
            st.warning("Please enter a company URL first.")
        else:
            st.session_state.ci_report = None
            prog = st.progress(0, text="Phase 1: Scraping website + sub-pages...")
            try:
                import threading
                import time as _t
                _result_holder = {}
                def _do_research():
                    try:
                        r = requests.post(
                            f"{BACKEND}/api/company-research",
                            json={"url": ci_url.strip()},
                            timeout=480,  # deep research can take several minutes
                        )
                        _result_holder["resp"] = r
                    except Exception as ex:
                        _result_holder["err"] = str(ex)

                t = threading.Thread(target=_do_research, daemon=True)
                t.start()
                steps = [
                    "Phase 1: Scraping website + sub-pages...",
                    "Phase 2: Searching ZaubaCorp / reviews / news...",
                    "Phase 3: Visiting public sources (MCP scrape)...",
                    "Phase 4: Azure OpenAI analysis...",
                    "Phase 5: Structuring report + citations...",
                ]
                # Poll until done — allow up to ~7 minutes total
                started = _t.time()
                max_wait = 420
                step_i = 0
                while t.is_alive() and (_t.time() - started) < max_wait:
                    elapsed = _t.time() - started
                    step_i = min(int(elapsed // 45), len(steps) - 1)
                    pct = min(95, int((elapsed / max_wait) * 100))
                    prog.progress(pct, text=f"{steps[step_i]} ({int(elapsed)}s)")
                    t.join(timeout=3)
                prog.progress(100, text="Done!")
                if "err" in _result_holder:
                    err = _result_holder["err"]
                    if "timed out" in err.lower() or "timeout" in err.lower():
                        st.error("Analysis took too long. Try again — backend is still warm now.")
                    else:
                        st.error(f"Request failed: {err}")
                elif "resp" not in _result_holder:
                    st.error("Still running after 7 minutes. Click Analyse again — cached sources may finish faster.")
                else:
                    r = _result_holder["resp"]
                    if r.status_code != 200:
                        st.error(f"Backend error {r.status_code}: {r.text[:300]}")
                    else:
                        st.session_state.ci_report = r.json()
                        st.rerun()
            except Exception as ex:
                st.error(f"Error: {ex}")

    # ── Report ──────────────────────────────────────────────────────────────
    report = st.session_state.get("ci_report")
    if report:
        if report.get("error"):
            st.error(report["error"])
            if report.get("raw"):
                st.code(report["raw"][:500])
        else:
            co  = report.get("company_profile", {})
            sc  = report.get("intelligence_score", {})

            # ── Hero banner ─────────────────────────────────────────────
            ind_raw = co.get("industry","")
            ind  = _val(ind_raw) if isinstance(ind_raw, dict) else str(ind_raw or "")
            hq_raw = co.get("headquarters","")
            hq   = _val(hq_raw) if isinstance(hq_raw, dict) else str(hq_raw or "")
            bull = " &bull; " + hq if _has_data(hq) else ""
            desc = co.get("description","")[:300] if isinstance(co.get("description"), str) else _val(co.get("description",""))[:300]
            summary = sc.get("summary","")
            st.markdown(
                "<div style='background:linear-gradient(135deg,#1e3a5f,#0f766e);"
                "border-radius:14px;padding:28px 32px;color:#fff;margin:16px 0 12px;'>"
                "<div style='font-size:26px;font-weight:800;margin-bottom:6px;'>"
                + str(co.get("name","Company")) +
                "<span style='font-size:13px;font-weight:400;opacity:.75;margin-left:12px;'>"
                + ind + bull + "</span></div>"
                "<div style='font-size:14px;opacity:.85;'>" + str(desc) + "</div>"
                + ("<div style='font-size:13px;opacity:.7;margin-top:10px;font-style:italic;'>"
                   + str(summary) + "</div>" if summary else "") +
                "</div>",
                unsafe_allow_html=True)

            # ── Perplexity-style Citations bar ──────────────────────────
            meta = report.get("_meta", {})
            citations = meta.get("citations", [])
            if not citations:
                # Fallback: build from available URLs
                citations = []
                if meta.get("queried_url"):
                    citations.append({
                        "title": "Company Website", "url": meta["queried_url"],
                        "domain": meta.get("domain",""),
                        "favicon": f"https://www.google.com/s2/favicons?domain={meta.get('domain','')}&sz=64",
                    })
                zurl = co.get("zaubacorp_url","")
                if zurl:
                    citations.append({
                        "title": "ZaubaCorp", "url": zurl, "domain": "zaubacorp.com",
                        "favicon": "https://www.google.com/s2/favicons?domain=zaubacorp.com&sz=64",
                    })

            n_src = len(citations)
            if n_src:
                # Overlapping favicon circles + "N sources"
                fav_html = ""
                for i, c in enumerate(citations[:4]):
                    fav = c.get("favicon") or f"https://www.google.com/s2/favicons?domain={c.get('domain','')}&sz=64"
                    left = i * 14
                    fav_html += (
                        f"<img src='{fav}' title='{c.get('domain','')}' "
                        f"style='width:22px;height:22px;border-radius:50%;"
                        f"border:2px solid #fff;position:absolute;left:{left}px;top:0;"
                        f"background:#e2e8f0;object-fit:cover;' "
                        f"onerror=\"this.style.display='none'\"/>"
                    )
                stack_w = min(n_src, 4) * 14 + 12
                cite_bar = (
                    "<div style='display:flex;align-items:center;gap:10px;"
                    "margin:0 0 18px 4px;flex-wrap:wrap;'>"
                    # action icons (visual only, like Perplexity)
                    "<span style='color:#94a3b8;font-size:15px;letter-spacing:8px;"
                    "user:select-none;'>&#8634; &#128190; &#128203;</span>"
                    # overlapping favicons
                    f"<div style='position:relative;width:{stack_w}px;height:22px;"
                    f"display:inline-block;vertical-align:middle;'>{fav_html}</div>"
                    # "N sources" text
                    f"<span style='font-size:13px;color:#64748b;font-weight:500;'>"
                    f"{n_src} source{'s' if n_src != 1 else ''}</span>"
                    "</div>"
                )
                st.markdown(cite_bar, unsafe_allow_html=True)

                # Expandable source list (Perplexity-style panel)
                with st.expander(f"Sources · {n_src} verified references", expanded=False):
                    # Horizontal source cards carousel
                    cards_html = (
                        "<div style='display:flex;gap:10px;overflow-x:auto;"
                        "padding:6px 2px 14px;scrollbar-width:thin;'>"
                    )
                    colors = ["#0f766e","#1d4ed8","#7c3aed","#d97706","#dc2626",
                              "#059669","#6366f1","#db2777"]
                    for i, c in enumerate(citations):
                        domain = c.get("domain") or urlparse(c.get("url","")).netloc.replace("www.","")
                        title  = (c.get("title") or domain)[:48]
                        cat    = c.get("category","Web")
                        fav    = c.get("favicon") or f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
                        url_c  = c.get("url","#")
                        accent = colors[i % len(colors)]
                        cards_html += (
                            f"<a href='{url_c}' target='_blank' rel='noopener' "
                            f"style='text-decoration:none;flex:0 0 220px;'>"
                            f"<div style='background:#fff;border:1px solid #e2e8f0;"
                            f"border-top:3px solid {accent};border-radius:12px;"
                            f"padding:12px;height:100px;overflow:hidden;"
                            f"box-shadow:0 1px 3px rgba(0,0,0,.04);'>"
                            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px;'>"
                            f"<img src='{fav}' style='width:18px;height:18px;border-radius:4px;' "
                            f"onerror=\"this.style.display='none'\"/>"
                            f"<span style='font-size:11px;color:#64748b;font-weight:600;'>"
                            f"{domain}</span></div>"
                            f"<div style='font-size:13px;color:#1e293b;font-weight:600;"
                            f"line-height:1.3;margin-bottom:4px;'>{title}</div>"
                            f"<div style='font-size:10px;color:#94a3b8;'>{cat}</div>"
                            f"</div></a>"
                        )
                    cards_html += "</div>"
                    st.markdown(cards_html, unsafe_allow_html=True)

                    # Numbered list like Perplexity sidebar
                    for i, c in enumerate(citations, 1):
                        domain = c.get("domain") or ""
                        title  = c.get("title") or domain
                        url_c  = c.get("url", "#")
                        cat    = c.get("category", "")
                        st.markdown(
                            f"<div style='display:flex;gap:10px;align-items:flex-start;"
                            f"padding:8px 0;border-bottom:1px solid #f1f5f9;'>"
                            f"<span style='background:#f1f5f9;color:#475569;border-radius:50%;"
                            f"width:22px;height:22px;display:inline-flex;align-items:center;"
                            f"justify-content:center;font-size:11px;font-weight:700;"
                            f"flex-shrink:0;'>{i}</span>"
                            f"<div style='flex:1;'>"
                            f"<a href='{url_c}' target='_blank' style='color:#0f766e;"
                            f"font-size:13px;font-weight:600;text-decoration:none;'>{title}</a>"
                            f"<div style='font-size:11px;color:#94a3b8;'>{domain}"
                            + (f" · {cat}" if cat else "") +
                            f"</div></div></div>",
                            unsafe_allow_html=True)

            # ── KPI bar ──────────────────────────────────────────────────
            founded_f  = co.get("founded", {})
            emp_f      = co.get("employee_count", {})
            rev_f      = co.get("annual_revenue", {})
            kpis = [
                ("&#127970;", "Founded",    _val(founded_f),  _cite(founded_f)),
                ("&#128101;", "Employees",  _val(emp_f),      _cite(emp_f)),
                ("&#128200;", "Revenue",    _val(rev_f),      _cite(rev_f)),
                ("&#127758;", "HQ",         hq[:35] if _has_data(hq) else "", ""),
                ("&#9733;",   "Score",      str(sc.get("overall","")) + "/100" if sc.get("overall") else "", ""),
            ]
            k_cols = st.columns(len(kpis))
            for col, (icon, label, val, cite) in zip(k_cols, kpis):
                if _has_data(val):
                    col.markdown(
                        "<div style='text-align:center;background:#f8fafc;"
                        "border-radius:10px;padding:12px 4px;border:1px solid #e2e8f0;'>"
                        "<div style='font-size:18px;'>" + icon + "</div>"
                        "<div style='font-size:10px;color:#64748b;margin:3px 0;'>" + label + "</div>"
                        "<div style='font-weight:700;color:#1e293b;font-size:12px;'>" + str(val)[:35] + "</div>"
                        + (cite if cite else "") +
                        "</div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Data Confidence Scorecard ─────────────────────────────────
            verified   = sc.get("verified_fields_count", "")
            estimated  = sc.get("estimated_fields_count", "")
            unverified = sc.get("unverified_fields_count", "")
            completeness = sc.get("data_completeness", "")
            reliability  = sc.get("source_reliability", "")
            if any([verified, estimated, completeness]):
                st.markdown(
                    "<div style='background:#fafafa;border:1px solid #e2e8f0;"
                    "border-radius:10px;padding:12px 18px;margin-bottom:16px;"
                    "display:flex;flex-wrap:wrap;gap:16px;align-items:center;'>"
                    "<span style='font-size:12px;font-weight:700;color:#475569;'>&#128203; DATA CONFIDENCE:</span>"
                    + (f"<span style='color:#16a34a;font-size:12px;'>&#9989; {verified} Verified</span>" if verified else "")
                    + (f"<span style='color:#d97706;font-size:12px;'>&#126; {estimated} Estimated</span>" if estimated else "")
                    + (f"<span style='color:#dc2626;font-size:12px;'>&#10067; {unverified} Unverified</span>" if unverified else "")
                    + (f"<span style='color:#3b82f6;font-size:12px;'>Completeness: {completeness}/100</span>" if completeness else "")
                    + (f"<span style='color:#8b5cf6;font-size:12px;'>Source Reliability: {reliability}/100</span>" if reliability else "")
                    + "</div>",
                    unsafe_allow_html=True)

            # ── Tabs ─────────────────────────────────────────────────────
            tab_labels = ["Overview", "Competitors", "People & Culture",
                          "News & Events", "SWOT", "Content Strategy",
                          "Risk & Finance", "&#128222; Contacts"]
            tabs = st.tabs(tab_labels)

            # TAB 0 — Overview
            with tabs[0]:
                prod = report.get("products_services", {})
                mkt  = report.get("market_analysis", {})
                tech = report.get("tech_stack", {})

                # ── MCA / ZaubaCorp official data badge ─────────────────
                mca_fields = {
                    "CIN":              _val(co.get("cin","")),
                    "MCA Status":       _val(co.get("mca_status","")),
                    "Authorized Capital": _val(co.get("authorized_capital","")),
                    "Paid-up Capital":  _val(co.get("paid_up_capital","")),
                    "RoC":              _val(co.get("roc","")),
                }
                mca_data = {k: v for k, v in mca_fields.items() if _has_data(v)}
                zauba_url = co.get("zaubacorp_url","") or ""
                if isinstance(zauba_url, dict):
                    zauba_url = _val(zauba_url)
                if mca_data:
                    mca_html  = "<div style='background:#f0fdf4;border:1.5px solid #16a34a;"
                    mca_html += "border-radius:10px;padding:14px 18px;margin-bottom:16px;'>"
                    mca_html += "<div style='font-weight:700;color:#166534;font-size:14px;"
                    mca_html += "margin-bottom:8px;'>&#9989; MCA Official Data (via ZaubaCorp)</div>"
                    mca_html += "<div style='display:flex;flex-wrap:wrap;gap:12px;'>"
                    for k, v in mca_data.items():
                        mca_html += ("<span style='background:#fff;border:1px solid #bbf7d0;"
                                     "border-radius:6px;padding:4px 10px;font-size:12px;'>"
                                     "<b>" + k + ":</b> " + str(v) + "</span>")
                    if zauba_url:
                        mca_html += ("<a href='" + zauba_url + "' target='_blank' "
                                     "style='font-size:12px;color:#0f766e;margin-left:8px;'>"
                                     "&#128279; View on ZaubaCorp</a>")
                    mca_html += "</div></div>"
                    st.markdown(mca_html, unsafe_allow_html=True)

                st.markdown("#### Products & Services")
                offerings = prod.get("primary_offerings", [])
                if isinstance(prod, dict) and isinstance(prod.get("value"), list) and not offerings:
                    offerings = prod.get("value")
                if offerings:
                    cols_p = st.columns(min(len(offerings), 3))
                    for i, o in enumerate(offerings[:6]):
                        if isinstance(o, dict):
                            label = str(o.get("item") or o.get("value") or o.get("name") or "")
                        else:
                            label = str(o)
                        if not label:
                            continue
                        cols_p[i % 3].markdown(
                            "<div style='background:#eff6ff;border-radius:8px;padding:10px;"
                            "margin-bottom:8px;font-size:13px;border-left:3px solid #3b82f6;'>"
                            + label + "</div>", unsafe_allow_html=True)
                else:
                    st.caption("No product/service list extracted yet.")
                for k in ["pricing_model","pricing_range","target_customers"]:
                    _row(k.replace("_"," ").title(), prod.get(k,""))
                clients = prod.get("notable_clients",[])
                if clients:
                    names = []
                    for c in clients:
                        if isinstance(c, dict):
                            names.append(str(c.get("name") or c.get("value") or ""))
                        else:
                            names.append(str(c))
                    names = [n for n in names if n]
                    if names:
                        st.markdown("**Notable Clients:** " + " &nbsp;|&nbsp; ".join(names))

                st.markdown("---")
                st.markdown("#### Market Position")
                for k in ["market_size_tam","market_position","market_share_estimate",
                           "growth_rate","geographic_reach"]:
                    _row(k.replace("_"," ").title(), mkt.get(k,""))
                diffs = mkt.get("key_differentiators",[])
                if diffs:
                    st.markdown("**Key Differentiators:**")
                    for d in diffs:
                        st.markdown(f"  - {d}")

                st.markdown("---")
                st.markdown("#### Website Technology")
                tech_note = tech.get("note","")
                if tech_note:
                    st.caption(tech_note)
                for k in ["website_cms","frontend_framework","analytics_tools",
                           "marketing_tools","company_erp_tools"]:
                    v = tech.get(k,"")
                    if isinstance(v, dict):
                        vv = _val(v)
                        if _has_data(vv):
                            st.markdown(f"- **{k.replace('_',' ').title()}:** {vv}{_cite(v)}",
                                        unsafe_allow_html=True)
                    elif isinstance(v, list) and v:
                        parts = []
                        for x in v:
                            if isinstance(x, dict):
                                parts.append(str(x.get("item") or x.get("value") or x))
                            else:
                                parts.append(str(x))
                        parts = [p for p in parts if p and "not publicly" not in p.lower()]
                        if parts:
                            st.markdown(f"- **{k.replace('_',' ').title()}:** {', '.join(parts)}")
                    elif v and "not publicly" not in str(v).lower():
                        st.markdown(f"- **{k.replace('_',' ').title()}:** {v}")
                if not any(tech.get(k) for k in ["website_cms","frontend_framework","analytics_tools"]):
                    st.caption("No website technology signals detected.")

            # TAB 1 — Competitors (fixed HTML, no f-string ternary)
            with tabs[1]:
                comps = report.get("competitors", [])
                threat_colors = {"High":"#fee2e2","Medium":"#fef3c7","Low":"#dcfce7"}
                threat_text   = {"High":"#dc2626","Medium":"#d97706","Low":"#16a34a"}
                if comps:
                    for c in comps:
                        if not isinstance(c, dict):
                            st.markdown(f"- {c}")
                            continue
                        cname  = str(c.get("name",""))
                        cdesc  = str(c.get("description",""))
                        cstr   = str(c.get("strengths",""))
                        cweak  = str(c.get("weaknesses",""))
                        cthreat= str(c.get("threat_level",""))
                        crev   = str(c.get("estimated_revenue",""))
                        tc = threat_colors.get(cthreat, "#f1f5f9")
                        tt = threat_text.get(cthreat, "#475569")

                        html  = "<div style='background:#fff;border:1px solid #e2e8f0;"
                        html += "border-left:4px solid #0f766e;border-radius:10px;"
                        html += "padding:16px;margin-bottom:12px;'>"
                        html += "<div style='display:flex;justify-content:space-between;"
                        html += "align-items:center;margin-bottom:8px;'>"
                        html += "<b style='color:#0f766e;font-size:15px;'>" + cname + "</b>"
                        if cthreat:
                            html += ("<span style='background:" + tc + ";color:" + tt +
                                     ";font-size:11px;font-weight:700;padding:2px 8px;"
                                     "border-radius:20px;'>" + cthreat + " Threat</span>")
                        html += "</div>"
                        if cdesc:
                            html += "<div style='color:#475569;font-size:13px;margin-bottom:6px;'>" + cdesc + "</div>"
                        if cstr:
                            html += "<div style='font-size:12px;color:#059669;'><b>Their Edge:</b> " + cstr + "</div>"
                        if cweak:
                            html += "<div style='font-size:12px;color:#dc2626;'><b>Their Weakness:</b> " + cweak + "</div>"
                        if crev and "not publicly" not in crev.lower():
                            html += "<div style='font-size:12px;color:#64748b;margin-top:4px;'>Revenue: " + crev + "</div>"
                        csrc = str(c.get("source") or "")
                        cconf = str(c.get("confidence") or "")
                        if csrc:
                            html += ("<div style='font-size:11px;color:#94a3b8;margin-top:6px;'>"
                                     + csrc + (" · " + cconf if cconf else "") + "</div>")
                        html += "</div>"
                        st.markdown(html, unsafe_allow_html=True)
                else:
                    st.info("No competitor data found.")

            # TAB 2 — People & Culture
            with tabs[2]:
                emp = report.get("employee_insights", {})
                leaders = report.get("leadership_team", [])

                if emp:
                    c1, c2 = st.columns(2)
                    left_keys  = ["total_employees","employee_growth_yoy","hiring_trend",
                                  "remote_policy","glassdoor_rating","ambitionbox_rating","ceo_approval"]
                    right_keys = ["culture_summary","pain_points","top_perks",
                                  "top_hiring_roles"]
                    with c1:
                        st.markdown("**Workforce Stats**")
                        for k in left_keys:
                            v = emp.get(k,"")
                            vv = _val(v) if isinstance(v, dict) else v
                            if _has_data(vv):
                                label = k.replace("_"," ").title()
                                color = "#16a34a" if k == "hiring_trend" and str(vv) == "Growing" else "#1e293b"
                                cite = _cite(v) if isinstance(v, dict) else ""
                                st.markdown(f"- **{label}:** <span style='color:{color}'>{vv}</span>{cite}",
                                            unsafe_allow_html=True)
                    with c2:
                        st.markdown("**Culture**")
                        cs = emp.get("culture_summary","")
                        csv = _val(cs) if isinstance(cs, dict) else cs
                        if _has_data(csv):
                            st.markdown(f"_{csv}_")
                        perks = emp.get("top_perks",[])
                        if perks:
                            st.markdown("**Top Perks:**")
                            for p in perks:
                                st.markdown(f"  - {p.get('item') if isinstance(p, dict) else p}")
                        pain = emp.get("pain_points",[])
                        if pain:
                            st.markdown("**Pain Points:**")
                            for p in pain:
                                st.markdown(f"  - {p.get('item') if isinstance(p, dict) else p}")
                        roles = emp.get("top_hiring_roles",[])
                        if roles:
                            st.markdown("**Actively Hiring For:**")
                            for r in roles:
                                st.markdown(f"  - {r.get('item') if isinstance(r, dict) else r}")
                    if not any(_has_data(_val(emp.get(k)) if isinstance(emp.get(k), dict) else emp.get(k))
                               for k in left_keys) and not _has_data(_val(emp.get("culture_summary")) if isinstance(emp.get("culture_summary"), dict) else emp.get("culture_summary")):
                        st.caption("Limited public workforce data found.")

                if leaders:
                    st.markdown("---")
                    st.markdown("**Leadership Team**")
                    l_cols = st.columns(min(len(leaders), 3))
                    for i, ldr in enumerate(leaders[:6]):
                        if isinstance(ldr, dict):
                            with l_cols[i % 3]:
                                st.markdown(
                                    "<div style='background:#f8fafc;border-radius:8px;"
                                    "padding:12px;border:1px solid #e2e8f0;margin-bottom:8px;'>"
                                    "<b style='color:#1e3a5f;'>" + str(ldr.get("name","")) + "</b><br>"
                                    "<span style='font-size:12px;color:#0f766e;font-weight:600;'>"
                                    + str(ldr.get("role","")) + "</span><br>"
                                    "<span style='font-size:12px;color:#64748b;'>"
                                    + str(ldr.get("background",""))[:120] + "</span>"
                                    "</div>", unsafe_allow_html=True)

            # TAB 3 — News & Events
            with tabs[3]:
                news_list = report.get("recent_news", [])
                sent_col  = {"Positive":"#dcfce7","Neutral":"#f1f5f9","Negative":"#fee2e2"}
                sent_text = {"Positive":"#166534","Neutral":"#475569","Negative":"#991b1b"}
                if news_list:
                    for n in news_list:
                        if not isinstance(n, dict):
                            st.markdown(f"- {n}")
                            continue
                        sent = str(n.get("sentiment","Neutral"))
                        bg   = sent_col.get(sent, "#f1f5f9")
                        tc2  = sent_text.get(sent, "#475569")
                        ntitle = str(n.get("title",""))
                        ndate  = str(n.get("date",""))
                        nsrc   = str(n.get("source",""))
                        nsum   = str(n.get("summary",""))
                        nimp   = str(n.get("impact",""))

                        html  = "<div style='background:" + bg + ";border-radius:10px;"
                        html += "padding:14px;margin-bottom:10px;border:1px solid #e2e8f0;'>"
                        html += "<div style='display:flex;justify-content:space-between;"
                        html += "align-items:flex-start;'>"
                        html += "<b style='font-size:14px;color:#1e293b;flex:1;'>" + ntitle + "</b>"
                        html += "<span style='background:#fff;color:" + tc2 + ";"
                        html += "font-size:11px;font-weight:700;padding:2px 8px;"
                        html += "border-radius:20px;margin-left:8px;white-space:nowrap;'>" + sent + "</span>"
                        html += "</div>"
                        meta_parts = []
                        if ndate: meta_parts.append(ndate)
                        if nsrc:  meta_parts.append(nsrc)
                        if nimp:  meta_parts.append("Impact: " + nimp)
                        if meta_parts:
                            html += "<div style='font-size:11px;color:#94a3b8;margin:4px 0;'>"
                            html += " &bull; ".join(meta_parts) + "</div>"
                        if nsum:
                            html += "<div style='font-size:13px;color:#475569;'>" + nsum + "</div>"
                        html += "</div>"
                        st.markdown(html, unsafe_allow_html=True)
                else:
                    st.info("No recent news found.")

            # TAB 4 — SWOT
            with tabs[4]:
                swot = report.get("swot_analysis", {})
                # Guard against Groq returning {"value":"Not publicly available"}
                if isinstance(swot, dict) and "strengths" not in swot and "value" in swot:
                    st.info("SWOT details were incomplete from AI — showing available summary.")
                    st.write(_val(swot) or "Not enough structured SWOT data.")
                    swot = {}
                if swot and any(swot.get(k) for k in ("strengths","weaknesses","opportunities","threats")):
                    sc1, sc2 = st.columns(2)
                    for col, key, bg, icon in [
                        (sc1, "strengths",    "#dcfce7", "&#9989;"),
                        (sc2, "weaknesses",   "#fee2e2", "&#10060;"),
                        (sc1, "opportunities","#dbeafe", "&#128640;"),
                        (sc2, "threats",      "#fef3c7", "&#9888;"),
                    ]:
                        items = swot.get(key, [])
                        if isinstance(items, str):
                            items = [{"point": items}]
                        bullets = ""
                        for item in items:
                            if isinstance(item, dict):
                                pt   = item.get("point", "")
                                src  = item.get("source", "")
                                conf = item.get("confidence", "")
                                if not pt or "not publicly" in str(pt).lower():
                                    continue
                                if "not publicly" in str(src).lower():
                                    src = "Analysis"
                                conf_color = {"High":"#16a34a","Medium":"#d97706","Low":"#dc2626"}.get(conf,"#94a3b8")
                                cite_badge = ""
                                if src:
                                    cite_badge += f"<span style='font-size:10px;color:#64748b;margin-left:4px;'>[{src}]</span>"
                                if conf:
                                    cite_badge += f"<span style='font-size:10px;color:{conf_color};font-weight:700;margin-left:3px;'>&#9679;{conf}</span>"
                                bullets += f"<div style='font-size:13px;margin-top:6px;'>&#8226; {pt}{cite_badge}</div>"
                            else:
                                if "not publicly" not in str(item).lower():
                                    bullets += f"<div style='font-size:13px;margin-top:5px;'>&#8226; {item}</div>"
                        if not bullets:
                            bullets = "<div style='font-size:12px;color:#94a3b8;margin-top:6px;'>Building from public signals...</div>"
                        col.markdown(
                            "<div style='background:" + bg + ";border-radius:10px;"
                            "padding:14px;margin-bottom:12px;'>"
                            "<b style='font-size:14px;'>" + icon + " " + key.title() + "</b>"
                            + bullets + "</div>",
                            unsafe_allow_html=True)
                else:
                    st.info("No SWOT data found.")

            # TAB 5 — Content Strategy
            with tabs[5]:
                cs = report.get("content_strategy", {})
                sm = report.get("social_media", {})
                if cs:
                    bv = cs.get("brand_voice","")
                    if bv:
                        st.markdown(f"**Brand Voice:** _{bv}_")
                    st.markdown("---")
                    pillars = cs.get("content_pillars",[])
                    if pillars:
                        st.markdown("**Content Pillars**")
                        p_cols = st.columns(min(len(pillars),4))
                        for i, p in enumerate(pillars[:4]):
                            p_cols[i % 4].markdown(
                                "<div style='background:#eff6ff;border-radius:8px;"
                                "padding:10px;text-align:center;font-size:13px;"
                                "font-weight:600;color:#1d4ed8;border:1px solid #bfdbfe;'>"
                                + str(p) + "</div>", unsafe_allow_html=True)
                    ideas = cs.get("viral_content_ideas",[])
                    if ideas:
                        st.markdown("---")
                        st.markdown("**Viral Content Ideas**")
                        for idea in ideas:
                            st.markdown(f"- {idea}")
                    tags = cs.get("top_hashtags",[])
                    if tags:
                        st.markdown("**Top Hashtags:** " + "  ".join(str(t) for t in tags))
                    gap = cs.get("competitor_content_gap","")
                    if gap:
                        st.info(f"**Content Gap Opportunity:** {gap}")

                if sm:
                    st.markdown("---")
                    st.markdown("**Social Media Presence**")
                    plats = ["linkedin","instagram","twitter_x","facebook","youtube"]
                    sm_cols = st.columns(len(plats))
                    for col, plat in zip(sm_cols, plats):
                        pd = sm.get(plat, {})
                        if isinstance(pd, dict) and pd.get("followers"):
                            al = pd.get("activity_level","")
                            al_color = {"High":"#16a34a","Medium":"#d97706","Low":"#dc2626"}.get(al,"#64748b")
                            col.markdown(
                                "<div style='text-align:center;background:#f8fafc;"
                                "border-radius:8px;padding:10px;border:1px solid #e2e8f0;'>"
                                "<div style='font-weight:700;font-size:13px;color:#1e293b;'>"
                                + plat.replace("_x","").replace("_"," ").title() + "</div>"
                                "<div style='font-size:12px;'>" + str(pd.get("followers","")) + "</div>"
                                "<div style='font-size:11px;color:" + al_color + ";'>" + al + "</div>"
                                "</div>", unsafe_allow_html=True)

            # TAB 6 — Risk & Finance
            with tabs[6]:
                fin  = report.get("financial_data", {}) or {}
                risk = report.get("risk_assessment", {}) or {}
                if fin:
                    st.markdown("**Financial Intelligence**")
                    fin_keys = ["funding_stage","total_funding","last_funding",
                                "last_funding_date","revenue_estimate","valuation_estimate",
                                "revenue_growth","profitability_status","stock_ticker",
                                "authorized_capital","paid_up_capital"]
                    shown = False
                    for k in fin_keys:
                        v = fin.get(k,"")
                        if isinstance(v, dict):
                            if _has_data(_val(v)):
                                _row(k.replace("_"," ").title(), v)
                                shown = True
                        elif v and "not publicly" not in str(v).lower():
                            st.markdown(f"- **{k.replace('_',' ').title()}:** {v}")
                            shown = True
                    investors = fin.get("key_investors",[])
                    if investors:
                        names = [str(i.get("name") if isinstance(i, dict) else i) for i in investors]
                        st.markdown("**Key Investors:** " + ", ".join(n for n in names if n))
                        shown = True
                    if not shown:
                        st.caption("Limited public financial disclosures found.")
                if risk:
                    st.markdown("---")
                    st.markdown("**Risk Assessment**")
                    rl = risk.get("overall_risk_level","")
                    if isinstance(rl, dict):
                        rl = _val(rl)
                    rl_color = {"High":"#dc2626","Medium":"#d97706","Low":"#16a34a"}.get(str(rl),"#64748b")
                    if rl:
                        st.markdown(f"**Overall Risk Level:** <span style='color:{rl_color};font-weight:700;'>{rl}</span>",
                                    unsafe_allow_html=True)
                    for cat in ["regulatory_risks","competitive_risks","operational_risks","reputational_risks"]:
                        items = risk.get(cat,[]) or []
                        if not items:
                            continue
                        st.markdown(f"**{cat.replace('_',' ').title()}:**")
                        for item in (items if isinstance(items, list) else [items]):
                            if isinstance(item, dict):
                                rsk = item.get("risk") or item.get("value") or ""
                                src = item.get("source") or ""
                                conf = item.get("confidence") or ""
                                if not rsk or "not enough public" in str(rsk).lower():
                                    continue
                                conf_c = {"High":"#16a34a","Medium":"#d97706","Low":"#dc2626"}.get(conf,"#64748b")
                                st.markdown(
                                    f"- {rsk} "
                                    f"<span style='font-size:11px;color:#94a3b8;'>[{src}]</span> "
                                    f"<span style='font-size:11px;color:{conf_c};font-weight:700;'>● {conf}</span>",
                                    unsafe_allow_html=True)
                            else:
                                if "not enough" not in str(item).lower():
                                    st.markdown(f"- {item}")

            # TAB 7 — Contacts
            with tabs[7]:
                import re as _re
                ci = report.get("contact_intelligence", {})
                conf_color = {"High":"#16a34a","Medium":"#d97706","Low":"#dc2626"}

                # Address
                addr = ci.get("registered_address","")
                addr_src = ci.get("address_source","")
                if _has_data(addr):
                    st.markdown(
                        "<div style='background:#f0fdf4;border:1.5px solid #16a34a;"
                        "border-radius:10px;padding:14px 18px;margin-bottom:16px;'>"
                        "<div style='font-weight:700;color:#166534;margin-bottom:4px;'>"
                        "&#127968; Registered Address</div>"
                        "<div style='color:#1e293b;font-size:14px;'>" + addr + "</div>"
                        + (f"<div style='font-size:11px;color:#64748b;margin-top:4px;'>Source: {addr_src}</div>" if addr_src else "")
                        + "</div>", unsafe_allow_html=True)

                # WhatsApp / Toll-free
                wa = ci.get("whatsapp","")
                tf = ci.get("toll_free","")
                if _has_data(wa) or _has_data(tf):
                    badges = ""
                    if _has_data(wa):
                        badges += (f"<span style='background:#dcfce7;color:#166534;"
                                   f"border-radius:20px;padding:4px 14px;font-size:13px;"
                                   f"font-weight:600;margin-right:8px;'>&#128241; WhatsApp: {wa}</span>")
                    if _has_data(tf):
                        badges += (f"<span style='background:#dbeafe;color:#1d4ed8;"
                                   f"border-radius:20px;padding:4px 14px;font-size:13px;"
                                   f"font-weight:600;'>&#128222; Toll-free: {tf}</span>")
                    st.markdown(badges + "<br>", unsafe_allow_html=True)

                # Phone numbers
                phones = ci.get("phones", [])
                if phones:
                    st.markdown("#### &#128222; Phone Numbers")
                    for ph in phones:
                        if not isinstance(ph, dict):
                            continue
                        num   = str(ph.get("number",""))
                        person = str(ph.get("person","") or "")
                        label = str(ph.get("label","General"))
                        if person and person not in label:
                            label = person
                        src   = str(ph.get("source",""))
                        conf  = str(ph.get("confidence","Medium"))
                        cc    = conf_color.get(conf,"#64748b")
                        label_colors = {
                            "Sales":"#1d4ed8","Support":"#7c3aed","HR":"#059669",
                            "CEO":"#dc2626","Export":"#d97706","Finance":"#0f766e",
                            "General":"#475569","Technical":"#6366f1","Media":"#db2777",
                            "Business":"#1d4ed8","Get In Touch":"#0f766e",
                        }
                        lc = next((v for k,v in label_colors.items() if k.lower() in label.lower()), "#0f766e")
                        who = f"<b style='color:#1e293b;'>{label}</b>" if label else ""
                        st.markdown(
                            "<div style='background:#fff;border:1px solid #e2e8f0;"
                            "border-radius:10px;padding:12px 16px;margin-bottom:8px;'>"
                            "<div style='display:flex;justify-content:space-between;align-items:center;'>"
                            "<div>"
                            "<span style='background:" + lc + "22;color:" + lc + ";"
                            "border-radius:20px;padding:2px 10px;font-size:11px;"
                            "font-weight:700;margin-right:10px;'>" + (label or "Contact") + "</span>"
                            "<a href='tel:" + _re.sub(r'[^\d+]','',num) + "' style='font-size:15px;"
                            "font-weight:700;color:#1e293b;font-family:monospace;"
                            "text-decoration:none;'>" + num + "</a>"
                            "</div>"
                            "<div style='text-align:right;'>"
                            "<span style='font-size:10px;color:#64748b;'>" + src + "</span>"
                            "<span style='font-size:10px;color:" + cc + ";font-weight:700;"
                            "margin-left:6px;'>&#9679; " + conf + "</span>"
                            "</div></div></div>", unsafe_allow_html=True)
                else:
                    st.info("No phone numbers found yet — scraper checks homepage footer, contact pages, and search.")

                # Email addresses
                emails = ci.get("emails", [])
                if emails:
                    st.markdown("#### &#128140; Email Addresses")
                    for em in emails:
                        if not isinstance(em, dict):
                            continue
                        email = str(em.get("email",""))
                        person = str(em.get("person","") or "")
                        label = str(em.get("label","General"))
                        src   = str(em.get("source",""))
                        conf  = str(em.get("confidence","Medium"))
                        cc    = conf_color.get(conf,"#64748b")
                        label_colors = {
                            "Sales":"#1d4ed8","Support":"#7c3aed","HR":"#059669",
                            "CEO":"#dc2626","Export":"#d97706","Finance":"#0f766e",
                            "General":"#475569","Business":"#1d4ed8","Career":"#059669",
                        }
                        lc = next((v for k,v in label_colors.items() if k.lower() in label.lower()), "#0f766e")
                        st.markdown(
                            "<div style='background:#fff;border:1px solid #e2e8f0;"
                            "border-radius:10px;padding:12px 16px;margin-bottom:8px;'>"
                            "<div style='display:flex;justify-content:space-between;align-items:center;'>"
                            "<div>"
                            "<span style='background:" + lc + "22;color:" + lc + ";"
                            "border-radius:20px;padding:2px 10px;font-size:11px;"
                            "font-weight:700;margin-right:10px;'>" + label + "</span>"
                            "<a href='mailto:" + email + "' style='font-size:14px;"
                            "color:#0f766e;font-weight:600;text-decoration:none;'>"
                            "&#128140; " + email + "</a>"
                            + (f"<div style='font-size:11px;color:#64748b;margin-top:2px;margin-left:4px;'>Person: {person}</div>" if person else "")
                            + "</div>"
                            "<div style='text-align:right;'>"
                            "<span style='font-size:10px;color:#64748b;'>" + src + "</span>"
                            "<span style='font-size:10px;color:" + cc + ";font-weight:700;"
                            "margin-left:6px;'>&#9679; " + conf + "</span>"
                            "</div></div></div>", unsafe_allow_html=True)
                else:
                    st.info("No email addresses found yet.")

                addrs = ci.get("addresses") or []
                if addrs and isinstance(addrs, list):
                    st.markdown("#### &#127968; Office Addresses")
                    for a in addrs:
                        st.markdown(
                            "<div style='background:#f8fafc;border:1px solid #e2e8f0;"
                            "border-radius:8px;padding:10px 14px;margin-bottom:6px;"
                            "font-size:13px;color:#334155;'>" + str(a) + "</div>",
                            unsafe_allow_html=True)

                if not phones and not emails and not _has_data(addr):
                    st.warning("No contact information was found. Sources checked: homepage footer, "
                               "/contact pages, DuckDuckGo, ZaubaCorp.")

            # Footer
            meta = report.get("_meta",{})
            gen_at  = meta.get("generated_at","")
            n_cite = meta.get("citation_count") or len(meta.get("citations") or [])
            if gen_at or n_cite:
                st.markdown(
                    "<div style='color:#94a3b8;font-size:11px;margin-top:20px;"
                    "border-top:1px solid #e2e8f0;padding-top:8px;'>"
                    + (f"{n_cite} sources verified" if n_cite else "")
                    + (" &nbsp;|&nbsp; " if n_cite and gen_at else "")
                    + (f"Generated: {gen_at}" if gen_at else "")
                    + "</div>", unsafe_allow_html=True)
