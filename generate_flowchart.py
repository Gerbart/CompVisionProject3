r"""
generate_flowchart.py  -  CV Project 3 Pipeline Flowchart
Run with:  dml_env\Scripts\python.exe generate_flowchart.py
Outputs:   pipeline_flowchart.png
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from PIL import Image
import numpy as np
import os

# ── Colour palette ────────────────────────────────────────────────────────────
BG      = '#0f1117'
CARD_UI = '#1e2230'
CARD_DL = '#1a2540'
CARD_CV = '#1a2a20'
CARD_3D = '#2a1a30'
BORDER_UI = '#4f8ef7'
BORDER_DL = '#f7c34f'
BORDER_CV = '#4fcf6e'
BORDER_3D = '#cf6ef7'
TEXT    = '#e8eaf0'
ARROW   = '#7f8caa'
ACCENT  = '#4f8ef7'

fig_w, fig_h = 22, 14
fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, fig_w)
ax.set_ylim(0, fig_h)
ax.axis('off')

# ─── Helper functions ─────────────────────────────────────────────────────────
def card(x, y, w, h, title, lines, bg, border, ax,
         title_size=9, body_size=7.5):
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle="round,pad=0.08",
                         facecolor=bg, edgecolor=border, linewidth=1.8,
                         zorder=3)
    ax.add_patch(box)
    # Title bar strip
    strip = FancyBboxPatch((x, y + h - 0.38), w, 0.38,
                           boxstyle="round,pad=0.04",
                           facecolor=border + '55', edgecolor='none',
                           zorder=4)
    ax.add_patch(strip)
    ax.text(x + w/2, y + h - 0.19, title,
            ha='center', va='center', fontsize=title_size, fontweight='bold',
            color=TEXT, zorder=5,
            path_effects=[pe.withStroke(linewidth=1, foreground='black')])
    for i, line in enumerate(lines):
        ax.text(x + 0.13, y + h - 0.62 - i * 0.32, line,
                ha='left', va='top', fontsize=body_size,
                color=TEXT + 'cc', zorder=5)

def arrow(ax, x1, y1, x2, y2, label='', color=ARROW):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color,
                                lw=1.6, connectionstyle='arc3,rad=0.0'),
                zorder=6)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx+0.05, my, label, fontsize=7, color=color+'cc',
                ha='left', va='center', zorder=7)

def darrow(ax, x1, y1, x2, y2, color=ARROW):
    """Diagonal / curved arrow."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color,
                                lw=1.6, connectionstyle='arc3,rad=0.18'),
                zorder=6)

# ─── Title ────────────────────────────────────────────────────────────────────
ax.text(fig_w/2, 13.55,
        'Semantic 3D Furniture Reconstruction  —  Pipeline Overview',
        ha='center', va='top', fontsize=16, fontweight='bold',
        color=TEXT, zorder=5,
        path_effects=[pe.withStroke(linewidth=2, foreground='#00000088')])

ax.text(fig_w/2, 13.1,
        'React + Vite Frontend   ·   FastAPI Backend   ·   PyTorch / DirectML (AMD GPU)',
        ha='center', va='top', fontsize=9, color=ARROW + 'dd', zorder=5)

# ─── Embed couch image (Step 0) ───────────────────────────────────────────────
img_path = os.path.join('public', 'couch_with_ottoman.png')
if os.path.exists(img_path):
    img = Image.open(img_path).convert('RGB')
    img.thumbnail((420, 280))
    img_arr = np.array(img)
    # Position inset
    newax = fig.add_axes([0.02, 0.62, 0.13, 0.20])   # [left,bottom,w,h] in fig frac
    newax.imshow(img_arr)
    newax.set_xticks([]); newax.set_yticks([])
    for sp in newax.spines.values():
        sp.set_edgecolor(BORDER_UI); sp.set_linewidth(2)
    newax.set_title('Input Image', fontsize=8, color=TEXT, pad=4)

# ─── STEP 1 – Upload & UI ────────────────────────────────────────────────────
x0, y0, cw, ch = 1.1, 9.8, 3.4, 2.8
card(x0, y0, cw, ch, '① Upload & UI Layer',
     ['Library: React 18 + Vite 5',
      'Library: model-viewer (Google)',
      '• Drag-&-drop image upload',
      '• Zoom / pan canvas (CSS transform)',
      '• Smart lasso selection tool',
      '• Add / subtract mask strokes'],
     CARD_UI, BORDER_UI, ax)

# ─── STEP 2 – Object Detection ───────────────────────────────────────────────
x1, y1 = 5.5, 9.8
card(x1, y1, 3.6, 2.8, '② Zero-Shot Object Detection',
     ['Model: OWL-ViT  (google/owlvit-base-patch32)',
      'Library: transformers (HuggingFace)',
      '• 20 furniture text queries',
      '• NMS (IoU > 0.5)',
      '• GrabCut segmentation (OpenCV)',
      '• Sorted by bounding-box area'],
     CARD_DL, BORDER_DL, ax)

# ─── STEP 3 – Smart Selection ────────────────────────────────────────────────
x2, y2 = 10.2, 9.8
card(x2, y2, 3.6, 2.8, '③ Smart Selection / GrabCut',
     ['Library: OpenCV (cv2.grabCut)',
      '• Lasso polygon  → cv2.fillPoly()',
      '• Add + Subtract strokes (hole-punch)',
      '• GrabCut RECT refinement',
      '• Returns: poly mask + GC mask',
      '• Live toggle (Pure / GrabCut)'],
     CARD_CV, BORDER_CV, ax)

# ─── STEP 4 – Inpainting ─────────────────────────────────────────────────────
x3, y3 = 15.0, 9.8
card(x3, y3, 3.8, 2.8, '④ Object Removal / Inpainting',
     ['OpenCV: cv2.inpaint (NS + Telea)',
      'AI: Stable Diffusion Inpainting',
      '    diffusers 0.30  ·  strength=0.30',
      '• Two-pass: OpenCV hint → SD refine',
      '• Context-aware background prompt',
      '• Poisson blend (seamlessClone)'],
     CARD_DL, BORDER_DL, ax)

# ─── STEP 5 – TripoSR Preprocessing ─────────────────────────────────────────
x4, y4 = 1.1, 5.8
card(x4, y4, 3.6, 2.8, '⑤ 3D Input Preprocessing',
     ['Library: OpenCV + Pillow',
      '• Mask erosion (shed shadows)',
      '• Tight RGBA crop to mask bbox',
      '• 20% whitespace margin added',
      '• White-bg composite (pure white)',
      '• Resize → 512×512 RGB'],
     CARD_CV, BORDER_CV, ax)

# ─── STEP 6 – TripoSR Inference ──────────────────────────────────────────────
x5, y5 = 5.5, 5.8
card(x5, y5, 3.8, 2.8, '⑥ TripoSR  (3D Generation)',
     ['Model: stabilityai/TripoSR',
      'Runtime: torch-directml  (AMD GPU)',
      '• Image tokeniser + Triplane ViT',
      '• Triplane → volume @ chunk_size=8192',
      '• Marching Cubes  (torchmcubes/CPU)',
      '• has_vertex_color=True  (textures)'],
     CARD_3D, BORDER_3D, ax)

# ─── STEP 7 – Mesh Post-process ──────────────────────────────────────────────
x6, y6 = 10.2, 5.8
card(x6, y6, 3.6, 2.8, '⑦ Mesh Post-Processing',
     ['Library: trimesh',
      '• Reload raw .glb from TripoSR',
      '• Apply –90° X-axis rotation',
      '    (trimesh.transformations)',
      '• Re-export → /temp/<id>.glb',
      '• Copy → /outputs/ (permanent)'],
     CARD_3D, BORDER_3D, ax)

# ─── STEP 8 – 3D Viewer ──────────────────────────────────────────────────────
x7, y7 = 15.0, 5.8
card(x7, y7, 3.8, 2.8, '⑧ 3D Preview & Export',
     ['Library: <model-viewer> v3.4 (Google)',
      '• Served via FastAPI /api/temp/',
      '• Auto-rotate + click-drag orbit',
      '• Vertex-colour texture display',
      '• .glb direct download button',
      '• Ambient + environment lighting'],
     CARD_UI, BORDER_UI, ax)

# ─── Horizontal arrows (top row) ─────────────────────────────────────────────
arrow(ax, x0+cw,       y0+ch/2, x1,       y1+ch/2,   'upload')
arrow(ax, x1+3.6,      y1+ch/2, x2,       y2+ch/2,   'detections')
arrow(ax, x2+3.6,      y2+ch/2, x3,       y3+ch/2,   'masks')

# ─── Vertical connectors (top → bottom row) ──────────────────────────────────
# Object selected → preprocessing
arrow(ax, x2+3.6/2,  y2,       x4+3.6/2, y4+2.8,   'selected obj')
# Inpainted → (re-used as new baseline shown in grey)
ax.annotate('', xy=(x3+3.8/2, y3), xytext=(x3+3.8/2, y4+2.8+0.1),
            arrowprops=dict(arrowstyle='->', color='#666688',
                            lw=1.2, linestyle='dashed'),
            zorder=5)
ax.text(x3+3.8/2+0.1, (y3+y4+2.8)/2, 'new baseline\n(re-upload)',
        fontsize=7, color='#888899', ha='left', va='center', zorder=5)

# ─── Horizontal arrows (bottom row) ──────────────────────────────────────────
arrow(ax, x4+3.6,   y4+ch/2, x5,        y5+ch/2,   '512×512 RGB')
arrow(ax, x5+3.8,   y5+ch/2, x6,        y6+ch/2,   'raw .glb')
arrow(ax, x6+3.6,   y6+ch/2, x7,        y7+ch/2,   'rotated .glb')

# ─── Legend ──────────────────────────────────────────────────────────────────
legend_items = [
    (BORDER_UI, 'UI / Frontend (React, model-viewer)'),
    (BORDER_DL, 'Deep Learning (OWL-ViT, Stable Diffusion)'),
    (BORDER_CV, 'Computer Vision (OpenCV, GrabCut)'),
    (BORDER_3D, '3D Pipeline (TripoSR, trimesh, DirectML)'),
]
lx, ly = 1.1, 4.8
for i, (col, label) in enumerate(legend_items):
    ax.add_patch(FancyBboxPatch((lx + i*5.2, ly), 4.9, 0.55,
                                boxstyle='round,pad=0.06',
                                facecolor=col+'22', edgecolor=col, linewidth=1.5,
                                zorder=3))
    ax.text(lx + i*5.2 + 2.45, ly+0.275, label,
            ha='center', va='center', fontsize=8, color=TEXT, zorder=5)

# ─── Tech stack footnote ─────────────────────────────────────────────────────
ax.text(fig_w/2, 0.35,
        'Stack: Python 3.12 · PyTorch (DirectML) · FastAPI · OpenCV · HuggingFace transformers · diffusers · trimesh · Pillow · React 18 · Vite 5',
        ha='center', va='bottom', fontsize=7.5, color=ARROW + '99', zorder=5)

out = 'pipeline_flowchart.png'
fig.savefig(out, dpi=150, bbox_inches='tight',
            facecolor=BG, edgecolor='none')
plt.close(fig)
print('Saved -> ' + out)
