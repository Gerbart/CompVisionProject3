import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ── Colour palette ────────────────────────────────────────────────────────────
# Neutral colors (no color-coding per section)
BG      = '#121212'
CARD    = '#222222'
BORDER  = '#888888'
TEXT    = '#ffffff'
ARROW   = '#aaaaaa'

fig_w, fig_h = 16, 22
fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, fig_w)
ax.set_ylim(0, fig_h)
ax.axis('off')

# ─── Helper functions ─────────────────────────────────────────────────────────
def card(x, y, w, h, summary, library, is_cv, ax):
    # x,y is center
    # CV nodes get thicker borders
    border_lw = 4 if is_cv else 1.5
    
    box = FancyBboxPatch((x - w/2, y - h/2), w, h,
                         boxstyle="round,pad=0.2",
                         facecolor=CARD, edgecolor=BORDER, linewidth=border_lw,
                         zorder=3)
    ax.add_patch(box)
    
    # Put summary first, bigger text
    summary_size = 18 if is_cv else 14
    lib_size = 14 if is_cv else 12
    
    # Summary
    ax.text(x, y + 0.2 * h, summary,
            ha='center', va='center', fontsize=summary_size, fontweight='bold',
            color=TEXT, zorder=5)
            
    # Library
    ax.text(x, y - 0.25 * h, library,
            ha='center', va='center', fontsize=lib_size, style='italic',
            color=TEXT + 'cc', zorder=5)

def arrow(ax, x1, y1, x2, y2, label=''):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->,head_width=0.6,head_length=0.8', color=ARROW, lw=4),
                zorder=2)
    if label:
        mx, my = (x1+x2)/2, (y1+y2)/2
        ax.text(mx + 0.3, my, label, fontsize=15, color=TEXT,
                ha='left', va='center', zorder=7,
                bbox=dict(facecolor=BG, edgecolor='none', pad=2))

# ─── Title ────────────────────────────────────────────────────────────────────
ax.text(fig_w/2, fig_h - 1.0,
        'Semantic 3D Furniture Reconstruction Pipeline',
        ha='center', va='center', fontsize=26, fontweight='bold',
        color=TEXT)

# ─── Nodes ────────────────────────────────────────────────────────────────────
cx = fig_w / 2
y_start = fig_h - 3.2
y_step = 2.8

# Sections compressed to focus on CV. Summaries are < 10 words.
nodes = [
    {
        "summary": "Handles image uploads and renders 3D results",
        "lib": "FastAPI / Vanilla JS",
        "cv": False,
        "label_out": "Image File"
    },
    {
        "summary": "Detects objects via zero-shot text queries",
        "lib": "OWL-ViT (PyTorch)",
        "cv": True,
        "label_out": "Bounding Boxes"
    },
    {
        "summary": "Extracts precise object pixel masks",
        "lib": "GrabCut (OpenCV)",
        "cv": True,
        "label_out": "Initial Binary Mask"
    },
    {
        "summary": "Refines masks using user-drawn polygons",
        "lib": "FillPoly (OpenCV)",
        "cv": True,
        "label_out": "Refined Pixel Mask"
    },
    {
        "summary": "Removes objects and generates background context",
        "lib": "Stable Diffusion / OpenCV Inpaint",
        "cv": True,
        "label_out": "Cleaned Workspace Image"
    },
    {
        "summary": "Converts isolated objects into 3D meshes",
        "lib": "TripoSR (DirectML)",
        "cv": True,
        "label_out": "Generated .glb File"
    }
]

y_curr = y_start
positions = []

for i, n in enumerate(nodes):
    h = 1.8 if n['cv'] else 1.2
    w = 11.0 if n['cv'] else 9.0
    
    card(cx, y_curr, w, h, n['summary'], n['lib'], n['cv'], ax)
    positions.append((cx, y_curr, h, w))
    
    if i < len(nodes) - 1:
        y_curr -= y_step

# Draw top-down arrows
for i in range(len(nodes)):
    if i < len(nodes) - 1:
        x1, y1, h1, _ = positions[i]
        x2, y2, h2, _ = positions[i+1]
        arrow(ax, x1, y1 - h1/2 - 0.05, x2, y2 + h2/2 + 0.05, nodes[i]['label_out'])

# Draw return loop (from 3D mesh generator back to UI)
x_last, y_last, h_last, w_last = positions[-1]
x_first, y_first, h_first, w_first = positions[0]

path_x = cx - w_last/2 - 1.5
ax.plot([cx - w_last/2, path_x, path_x, cx - w_first/2 - 0.5], 
        [y_last, y_last, y_first, y_first], color=ARROW, lw=4, zorder=2)
ax.annotate('', xy=(cx - w_first/2, y_first), xytext=(cx - w_first/2 - 0.5, y_first), 
            arrowprops=dict(arrowstyle='->,head_width=0.6,head_length=0.8', color=ARROW, lw=4), zorder=2)

ax.text(path_x - 0.2, (y_first + y_last)/2, nodes[-1]['label_out'], 
        fontsize=15, color=TEXT, ha='right', va='center', rotation=90,
        bbox=dict(facecolor=BG, edgecolor='none', pad=2))

out = 'pipeline_flowchart.png'
fig.savefig(out, dpi=200, bbox_inches='tight', facecolor=BG, edgecolor='none')
plt.close(fig)
print('Saved -> ' + out)
