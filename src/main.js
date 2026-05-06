const API_URL = 'http://localhost:8000/api';

const state = {
  imageId: null,
  detectedObjects: [],
  selectedObjectId: null,
  // Single source of truth for the committed (non-hover) workspace image
  committedSrc: null,
  mode: 'remove'
};

// Elements
const imageWorkspace = document.getElementById('image-workspace');
const bboxContainer  = document.getElementById('bbox-container');
const objectsContainer = document.getElementById('objects-container');
const optionsContainer = document.getElementById('options-container');
const btnActionPrimary = document.getElementById('btn-action-primary');

// ─────────────────────────────────────────────────────────
//  Navigation
// ─────────────────────────────────────────────────────────
function goToWorkspace() {
  document.getElementById('step-upload').classList.remove('active');
  document.getElementById('step-workspace').classList.add('active');
}

// ─────────────────────────────────────────────────────────
//  Upload
// ─────────────────────────────────────────────────────────
const fileInput  = document.getElementById('file-input');
const dropZone   = document.getElementById('drop-zone');
const uploadText = document.getElementById('upload-text');

dropZone.addEventListener('click',    () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--primary)'; });
dropZone.addEventListener('dragleave',(e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--glass-border)'; });
dropZone.addEventListener('drop',     (e) => { e.preventDefault(); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]); });
fileInput.addEventListener('change',  (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); });

async function handleFile(file) {
  uploadText.innerText = 'Analyzing scene…';
  try {
    const formData = new FormData();
    formData.append('file', file);

    const uploadData = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData }).then(r => r.json());
    state.imageId = uploadData.image_id;

    const analyzeData = await fetch(`${API_URL}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: state.imageId })
    }).then(r => r.json());

    state.detectedObjects = analyzeData.objects;

    // Set committed src first, then show workspace once image loads
    const reader = new FileReader();
    reader.onload = (e) => {
      state.committedSrc  = e.target.result;
      imageWorkspace.src  = e.target.result;
      imageWorkspace.onload = () => { renderObjects(); goToWorkspace(); };
    };
    reader.readAsDataURL(file);
  } catch (err) {
    console.error(err);
    alert('Failed to connect to backend.');
    uploadText.innerText = 'Drag & Drop Image';
  }
}

// ─────────────────────────────────────────────────────────
//  Object selection
// ─────────────────────────────────────────────────────────
function selectObject(id) {
  state.selectedObjectId = id;

  document.querySelectorAll('.object-card').forEach(c => c.classList.remove('selected'));
  document.querySelectorAll('.bounding-box').forEach(b => b.classList.remove('selected'));

  if (id) {
    document.getElementById(`card-${id}`)?.classList.add('selected');
    document.getElementById(`bbox-${id}`)?.classList.add('selected');
    btnActionPrimary.disabled = false;

    // Show green mask overlay for the selected object
    const obj = state.detectedObjects.find(o => o.id === id);
    if (obj && obj.cutout_b64 && !drawMode) {
      // Fetch the full-image mask from backend to show proper overlay
      if (obj.mask_id) {
        fetch(`${API_URL}/temp/${obj.mask_id}`)
          .then(r => r.blob())
          .then(blob => {
            const url = URL.createObjectURL(blob);
            resizeSelCanvas();
            showMaskOverlay(url);
            URL.revokeObjectURL(url);
          })
          .catch(() => {}); // silently fail — overlay is cosmetic
      }
    }
  } else {
    btnActionPrimary.disabled = true;
    // Clear the overlay when nothing is selected
    if (!drawMode) selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
  }
}

// ─────────────────────────────────────────────────────────
//  Render objects list + bounding boxes
// ─────────────────────────────────────────────────────────
function renderObjects() {
  objectsContainer.innerHTML = '';
  bboxContainer.innerHTML    = '';

  const natW = imageWorkspace.naturalWidth;
  const natH = imageWorkspace.naturalHeight;

  if (state.detectedObjects.length === 0) {
    objectsContainer.innerHTML = '<div class="empty-state">No objects detected. Try another image.</div>';
    return;
  }

  state.detectedObjects.forEach(obj => {
    // Sidebar card
    const card = document.createElement('div');
    card.className = 'object-card';
    card.id = `card-${obj.id}`;
    card.innerHTML = `
      <img src="${obj.cutout_b64}" alt="${obj.label}">
      <div class="obj-info">
        <div class="obj-label">${obj.label}</div>
        <div class="obj-id">Object #${obj.id.substring(0, 4)}</div>
      </div>
    `;
    card.addEventListener('click', () => selectObject(obj.id));
    card.addEventListener('mouseenter', () => {
      document.getElementById(`bbox-${obj.id}`)?.style.setProperty('border-color', 'white');
    });
    card.addEventListener('mouseleave', () => {
      if (state.selectedObjectId !== obj.id)
        document.getElementById(`bbox-${obj.id}`)?.style.setProperty('border-color', 'rgba(255,255,255,0.6)');
    });
    objectsContainer.appendChild(card);

    // Bounding box overlay
    const [x, y, w, h] = obj.box;
    const bbox = document.createElement('div');
    bbox.className = 'bounding-box';
    bbox.id = `bbox-${obj.id}`;
    bbox.style.left   = `${(x / natW) * 100}%`;
    bbox.style.top    = `${(y / natH) * 100}%`;
    bbox.style.width  = `${(w / natW) * 100}%`;
    bbox.style.height = `${(h / natH) * 100}%`;
    bbox.addEventListener('click', (e) => { e.stopPropagation(); selectObject(obj.id); });
    bbox.addEventListener('mouseenter', () => card.style.borderColor = 'white');
    bbox.addEventListener('mouseleave', () => {
      if (state.selectedObjectId !== obj.id) card.style.borderColor = 'transparent';
    });
    bboxContainer.appendChild(bbox);
  });
}

// Click image background to deselect
imageWorkspace.addEventListener('click', () => selectObject(null));

// ─────────────────────────────────────────────────────────
//  Zoom + Pan (cursor-relative, smooth)
// ─────────────────────────────────────────────────────────
const zoomWrapper    = document.getElementById('zoom-wrapper');
const mainContainer  = document.getElementById('main-container');

let scale    = 1;
let panX     = 0;   // translation in screen px (applied before scale)
let panY     = 0;
let isPanning = false;
let panStartX = 0;
let panStartY = 0;

function applyTransform() {
  // transform-origin stays at (0,0); we use translate() then scale()
  // A point at element-space (ex,ey) maps to screen: (panX + ex*scale, panY + ey*scale)
  zoomWrapper.style.transformOrigin = '0 0';
  zoomWrapper.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
}

mainContainer.addEventListener('wheel', (e) => {
  e.preventDefault();

  const oldScale = scale;
  const delta    = e.deltaY < 0 ? 0.15 : -0.15;
  scale = Math.min(15, Math.max(1, scale + delta));

  if (scale === 1) {
    panX = 0; panY = 0;
    applyTransform();
    return;
  }

  // Keep the point under cursor fixed:
  // mouse_screen = panX + mouseEl * scale   (before)
  // mouse_screen = newPanX + mouseEl * newScale  (after)
  // => newPanX = panX + mouseEl * (scale - oldScale)
  // where mouseEl = (mouse_screen - panX) / oldScale
  const rect   = mainContainer.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;   // screen px relative to container
  const mouseY = e.clientY - rect.top;
  const elX    = (mouseX - panX) / oldScale;
  const elY    = (mouseY - panY) / oldScale;
  panX = mouseX - elX * scale;
  panY = mouseY - elY * scale;

  applyTransform();
}, { passive: false });

// Drag to pan (only when zoomed in and not in draw mode)
mainContainer.addEventListener('mousedown', (e) => {
  if (scale <= 1 || drawMode || e.button !== 0) return;
  isPanning  = true;
  panStartX  = e.clientX - panX;
  panStartY  = e.clientY - panY;
  mainContainer.style.cursor = 'grabbing';
});
window.addEventListener('mousemove', (e) => {
  if (!isPanning) return;
  panX = e.clientX - panStartX;
  panY = e.clientY - panStartY;
  applyTransform();
});
window.addEventListener('mouseup', () => {
  isPanning = false;
  mainContainer.style.cursor = '';
});

// ─────────────────────────────────────────────────────────
//  Commit a new workspace image (updates state + element)
// ─────────────────────────────────────────────────────────
function commitImage(src) {
  state.committedSrc = src;
  imageWorkspace.src = src;
}

// ─────────────────────────────────────────────────────────
//  Primary action button
// ─────────────────────────────────────────────────────────
btnActionPrimary.addEventListener('click', async () => {
  btnActionPrimary.disabled = true;

  // ── Removal mode ──
  if (state.mode === 'remove') {
    const selectedObj = state.detectedObjects.find(o => o.id === state.selectedObjectId);
    if (!selectedObj) { btnActionPrimary.disabled = false; return; }

    document.getElementById('loading-removal').classList.remove('hidden');
    optionsContainer.innerHTML = '';
    btnActionPrimary.innerText = 'Removing...';
    // Clear any selection overlay so the user can see the inpainted result clearly
    selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);

    try {
      const useAi = document.getElementById('checkbox-use-ai').checked;
      const data  = await fetch(`${API_URL}/inpaint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_id: state.imageId,
          mask_id:  selectedObj.mask_id,
          num_options: 3,
          use_ai: useAi
        })
      }).then(r => r.json());

      document.getElementById('loading-removal').classList.add('hidden');

      data.options.forEach((b64) => {
        const div = document.createElement('div');
        div.className = 'option-card';
        div.innerHTML = `<img src="${b64}" alt="Option">`;

        // Hover preview — restore to committed src on leave, clear overlay while hovering
        div.addEventListener('mouseenter', () => {
          imageWorkspace.src = b64;
          selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
        });
        div.addEventListener('mouseleave', () => {
          if (!div.classList.contains('selected'))
            imageWorkspace.src = state.committedSrc;
          // Restore overlay for the selected object if any
          if (state.selectedObjectId) selectObject(state.selectedObjectId);
        });

        div.addEventListener('click', async () => {
          // 1. Immediately commit this image as the new baseline
          commitImage(b64);

          // 2. Remove object from sidebar / bboxes
          state.detectedObjects = state.detectedObjects.filter(o => o.id !== selectedObj.id);
          renderObjects();
          selectObject(null);

          // 3. Mark card as selected visually
          document.querySelectorAll('.option-card').forEach(c => c.classList.remove('selected'));
          div.classList.add('selected');

          // 4. Upload committed image to backend (async — does NOT block UI)
          const blobRes  = await fetch(b64);
          const blob     = await blobRes.blob();
          const file     = new File([blob], 'inpainted.png', { type: 'image/png' });
          const formData = new FormData();
          formData.append('file', file);
          const uploadData = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData }).then(r => r.json());
          state.imageId = uploadData.image_id;

          setTimeout(() => {
            optionsContainer.innerHTML = '<div class="empty-state">Select another object to remove, or click Done.</div>';
          }, 1500);
        });

        optionsContainer.appendChild(div);
      });
    } catch (err) {
      console.error(err);
      alert('Inpainting failed.');
      document.getElementById('loading-removal').classList.add('hidden');
    }

    btnActionPrimary.innerText  = 'Remove Selected Object';
    btnActionPrimary.disabled   = false;

  // ── 3D Generation mode ──
  } else {
    const selectedObj = state.detectedObjects.find(o => o.id === state.selectedObjectId);
    if (!selectedObj) { btnActionPrimary.disabled = false; return; }

    document.querySelector('#loading-3d p').innerText = 'Running TripoSR (DirectML)…';
    document.getElementById('loading-3d').classList.remove('hidden');
    btnActionPrimary.innerText = 'Generating 3D…';

    try {
      const data = await fetch(`${API_URL}/generate_3d`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: state.imageId, mask_id: selectedObj.mask_id })
      }).then(r => r.json());

      document.getElementById('loading-3d').classList.add('hidden');

      const viewer = document.getElementById('result-3d-model');
      if (viewer) viewer.src = data.model_url;

      document.getElementById('final-state').classList.remove('hidden');
    } catch (err) {
      console.error(err);
      alert('3D Generation failed. Check the terminal for details.');
    }

    btnActionPrimary.innerText = 'Generate 3D Model';
    btnActionPrimary.disabled  = false;
  }
});

// ─────────────────────────────────────────────────────────
//  Done Removing → switch to 3D mode
// ─────────────────────────────────────────────────────────
document.getElementById('btn-done-removal').addEventListener('click', () => {
  state.mode = '3d';
  selectObject(null);

  // Clear the smart-selection canvas so it doesn't bleed into 3D mode
  if (typeof selCtx !== 'undefined') selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
  drawMode = false;
  selCanvas.classList.remove('drawing');

  document.getElementById('checkbox-use-ai').parentElement.style.display = 'none';

  document.getElementById('sidebar-removal').classList.remove('active');
  document.getElementById('sidebar-removal').classList.add('hidden');
  document.getElementById('sidebar-3d').classList.remove('hidden');
  document.getElementById('sidebar-3d').classList.add('active');

  document.getElementById('workspace-title').innerHTML =
    `Step 2: <span class="gradient-text text-green">Select Target Object</span>`;
  document.getElementById('workspace-desc').innerText =
    'Select the object you want to convert into a 3D model.';
  btnActionPrimary.innerText  = 'Generate 3D Model';
  btnActionPrimary.disabled   = false;
});

// ─────────────────────────────────────────────────────────
//  Start Over — full in-place state reset
// ─────────────────────────────────────────────────────────
function resetToUpload() {
  // Reset state
  state.imageId    = null;
  state.detectedObjects = [];
  state.selectedObjectId = null;
  state.committedSrc = null;
  state.mode       = 'remove';
  smartGcData      = null;
  smartPolyData    = null;
  smartMaskId      = null;
  document.getElementById('label-pure-selection').style.display = 'none';
  document.getElementById('checkbox-pure-selection').checked    = false;

  // Reset zoom/pan
  scale = 1; panX = 0; panY = 0;
  applyTransform();

  // Clear canvas
  selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
  drawMode = false;
  selCanvas.classList.remove('drawing');
  bboxContainer.style.pointerEvents = '';

  // Clear file input so the same file triggers 'change' again
  fileInput.value = '';

  // Reset UI containers
  objectsContainer.innerHTML = '';
  bboxContainer.innerHTML    = '';
  optionsContainer.innerHTML = '';
  imageWorkspace.src         = '';

  // Reset sidebar
  document.getElementById('sidebar-removal').classList.add('active');
  document.getElementById('sidebar-removal').classList.remove('hidden');
  document.getElementById('sidebar-3d').classList.add('hidden');
  document.getElementById('sidebar-3d').classList.remove('active');
  document.getElementById('checkbox-use-ai').parentElement.style.display = '';
  document.getElementById('final-state')?.classList.add('hidden');
  document.getElementById('loading-3d')?.classList.add('hidden');
  document.getElementById('loading-removal')?.classList.add('hidden');

  // Reset buttons
  btnActionPrimary.innerText = 'Remove Selected Object';
  btnActionPrimary.disabled  = true;
  btnDrawSelect.innerText    = '✏️ Draw Selection';
  btnDrawSelect.classList.remove('btn-primary');
  btnDrawSelect.classList.add('btn-secondary');

  // Reset workspace title
  document.getElementById('workspace-title').innerHTML =
    `Step 1: <span class="gradient-text">Select Objects to Remove</span>`;
  document.getElementById('workspace-desc').innerText =
    'Click on an object in the panel to select it, then click Remove.';

  uploadText.innerText = 'Drag & Drop Image';

  // Go back to upload screen
  document.getElementById('step-workspace').classList.remove('active');
  document.getElementById('step-upload').classList.add('active');
}

// ─────────────────────────────────────────────────────────
//  Shared: return from 3D mode → Removal mode
// ─────────────────────────────────────────────────────────
function goBackToRemoval() {
  state.mode = 'remove';

  document.getElementById('final-state')?.classList.add('hidden');
  document.getElementById('loading-3d')?.classList.add('hidden');

  document.getElementById('sidebar-3d').classList.remove('active');
  document.getElementById('sidebar-3d').classList.add('hidden');
  document.getElementById('sidebar-removal').classList.remove('hidden');
  document.getElementById('sidebar-removal').classList.add('active');
  document.getElementById('checkbox-use-ai').parentElement.style.display = '';

  renderObjects();

  document.getElementById('workspace-title').innerHTML =
    `Step 1: <span class="gradient-text">Select Objects to Remove</span>`;
  document.getElementById('workspace-desc').innerText =
    'Click on an object in the panel to select it, then click Remove.';
  btnActionPrimary.innerText = 'Remove Selected Object';
  btnActionPrimary.disabled  = true;
  selectObject(null);
}

// ← Back button: smart back navigation
// - In 3D mode   → goBackToRemoval()
// - In removal mode → go all the way back to upload
document.getElementById('btn-start-over').addEventListener('click', () => {
  if (state.mode === '3d') {
    goBackToRemoval();
  } else {
    resetToUpload();
  }
});

// ─────────────────────────────────────────────────────────
//  Export .GLB
// ─────────────────────────────────────────────────────────
document.getElementById('btn-export-3d').addEventListener('click', () => {
  const viewer = document.getElementById('result-3d-model');
  if (viewer?.src) {
    const a = document.createElement('a');
    a.href = viewer.src;
    a.download = 'generated_model.glb';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
});

// ─────────────────────────────────────────────────────────
//  Smart Selection Canvas Tool (Draw Mode)
// ─────────────────────────────────────────────────────────
const selCanvas     = document.getElementById('selection-canvas');
const selCtx        = selCanvas.getContext('2d');
const btnDrawSelect = document.getElementById('btn-draw-select');

let drawMode       = false;
let isDrawing      = false;
let drawSubtract   = false;     // true = current stroke is subtracting
let currentStroke  = [];        // points for the stroke being drawn right now
let addStrokes     = [];        // committed ADD polygon strokes  [[{x,y,fx,fy}...]]
let subtractStrokes = [];       // committed SUBTRACT polygon strokes
let brushRadius    = 18;
let smartMaskId    = null;
let smartGcData    = null;
let smartPolyData  = null;

// Sync canvas resolution to its CSS size
function resizeSelCanvas() {
  selCanvas.width  = selCanvas.offsetWidth;
  selCanvas.height = selCanvas.offsetHeight;
}

// Marching-ants animated dashed outline
let antOffset = 0;
function animateAnts() {
  if (!drawMode) return;
  antOffset = (antOffset + 0.5) % 16;
  redrawCanvas();
  requestAnimationFrame(animateAnts);
}

function redrawCanvas() {
  selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);

  // Draw all committed add strokes (green fill)
  for (const stroke of addStrokes) {
    if (stroke.length < 2) continue;
    selCtx.beginPath();
    selCtx.moveTo(stroke[0].x, stroke[0].y);
    for (let i = 1; i < stroke.length; i++) selCtx.lineTo(stroke[i].x, stroke[i].y);
    selCtx.closePath();
    selCtx.fillStyle = 'rgba(16, 185, 129, 0.22)';
    selCtx.fill();
    selCtx.setLineDash([8, 8]);
    selCtx.lineDashOffset = -antOffset;
    selCtx.strokeStyle = '#10b981';
    selCtx.lineWidth = 2;
    selCtx.stroke();
    selCtx.setLineDash([]);
  }

  // Draw all committed subtract strokes (red fill)
  for (const stroke of subtractStrokes) {
    if (stroke.length < 2) continue;
    selCtx.beginPath();
    selCtx.moveTo(stroke[0].x, stroke[0].y);
    for (let i = 1; i < stroke.length; i++) selCtx.lineTo(stroke[i].x, stroke[i].y);
    selCtx.closePath();
    selCtx.fillStyle = 'rgba(239, 68, 68, 0.22)';
    selCtx.fill();
    selCtx.setLineDash([8, 8]);
    selCtx.lineDashOffset = -antOffset;
    selCtx.strokeStyle = '#ef4444';
    selCtx.lineWidth = 2;
    selCtx.stroke();
    selCtx.setLineDash([]);
  }

  // Draw current in-progress stroke
  if (currentStroke.length >= 2) {
    selCtx.beginPath();
    selCtx.moveTo(currentStroke[0].x, currentStroke[0].y);
    for (let i = 1; i < currentStroke.length; i++) selCtx.lineTo(currentStroke[i].x, currentStroke[i].y);
    selCtx.fillStyle = drawSubtract ? 'rgba(239,68,68,0.12)' : 'rgba(16,185,129,0.12)';
    selCtx.fill();
    selCtx.setLineDash([4, 4]);
    selCtx.strokeStyle = drawSubtract ? '#ef4444' : '#10b981';
    selCtx.lineWidth = 1.5;
    selCtx.stroke();
    selCtx.setLineDash([]);
  }
}

function enterDrawMode() {
  drawMode      = true;
  addStrokes    = [];
  subtractStrokes = [];
  currentStroke = [];
  drawSubtract  = false;
  smartMaskId   = null;
  selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
  selCanvas.classList.add('drawing');
  btnDrawSelect.innerText = '✅ Confirm Selection';
  btnDrawSelect.classList.add('btn-primary');
  btnDrawSelect.classList.remove('btn-secondary');
  bboxContainer.style.pointerEvents = 'none';
  document.querySelectorAll('.bounding-box').forEach(b => b.style.pointerEvents = 'none');
  selectObject(null);
  // Show/style the subtract toggle
  document.getElementById('btn-subtract-mode').style.display = 'inline-flex';
  document.getElementById('btn-subtract-mode').classList.remove('active-subtract');
  animateAnts();
}

// ─── Helper: blit a b64 mask onto selCanvas as green tint ──────────────────
function showMaskOverlay(maskB64) {
  const maskImg = new window.Image();
  maskImg.onload = () => {
    const offscreen  = document.createElement('canvas');
    offscreen.width  = selCanvas.width;
    offscreen.height = selCanvas.height;
    const offCtx = offscreen.getContext('2d');
    offCtx.drawImage(maskImg, 0, 0, selCanvas.width, selCanvas.height);
    const imgData = offCtx.getImageData(0, 0, selCanvas.width, selCanvas.height);
    const d = imgData.data;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i] > 128) {
        d[i] = 16; d[i+1] = 185; d[i+2] = 129; d[i+3] = 140; // green tint
      } else {
        d[i+3] = 0; // transparent
      }
    }
    selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
    selCtx.putImageData(imgData, 0, 0);
  };
  maskImg.src = maskB64;
}

async function confirmDrawMode() {
  drawMode = false;
  selCanvas.classList.remove('drawing');
  bboxContainer.style.pointerEvents = '';
  document.getElementById('btn-subtract-mode').style.display = 'none';

  if (addStrokes.length === 0 || !state.imageId) {
    exitDrawMode();
    return;
  }

  btnDrawSelect.innerText  = '⏳ Processing…';
  btnDrawSelect.disabled   = true;

  // Send all strokes to backend
  const addPts = addStrokes.map(s => s.map(p => [p.fx, p.fy]));
  const subPts = subtractStrokes.map(s => s.map(p => [p.fx, p.fy]));

  try {
    const data = await fetch(`${API_URL}/smart_mask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_id:        state.imageId,
        add_strokes:     addPts,
        subtract_strokes: subPts,
        // Legacy single-stroke field (first add stroke) for backward compat
        points: addPts[0] || [],
      })
    }).then(r => r.json());

    smartGcData   = { mask_id: data.mask_id,      mask_b64: data.mask_b64 };
    smartPolyData = { mask_id: data.poly_mask_id, mask_b64: data.poly_mask_b64 };

    const usePure = document.getElementById('checkbox-pure-selection').checked;
    const active  = usePure ? smartPolyData : smartGcData;
    smartMaskId   = active.mask_id;
    showMaskOverlay(active.mask_b64);
    document.getElementById('label-pure-selection').style.display = 'flex';

    const smartObj = {
      id:         'smart-sel',
      label:      'Custom Selection',
      box:        [0, 0, 1, 1],
      mask_id:    smartMaskId,
      cutout_b64: active.mask_b64,
    };
    state.detectedObjects = state.detectedObjects.filter(o => o.id !== 'smart-sel');
    state.detectedObjects.unshift(smartObj);
    renderObjects();
    selectObject('smart-sel');

  } catch (err) {
    console.error(err);
    alert('Smart selection failed.');
  }

  btnDrawSelect.innerText  = '✏️ Draw Selection';
  btnDrawSelect.classList.remove('btn-primary');
  btnDrawSelect.classList.add('btn-secondary');
  btnDrawSelect.disabled = false;
}

// Live toggle: switch between GrabCut and pure polygon mask
document.getElementById('checkbox-pure-selection').addEventListener('change', (e) => {
  if (!smartGcData || !smartPolyData) return;
  const active = e.target.checked ? smartPolyData : smartGcData;
  smartMaskId  = active.mask_id;
  showMaskOverlay(active.mask_b64);
  // Update the smart-sel object so remove uses the newly chosen mask
  const smartObj = state.detectedObjects.find(o => o.id === 'smart-sel');
  if (smartObj) {
    smartObj.mask_id    = smartMaskId;
    smartObj.cutout_b64 = active.mask_b64;
  }
  if (state.selectedObjectId === 'smart-sel') selectObject('smart-sel');
});

function exitDrawMode() {
  drawMode      = false;
  addStrokes    = [];
  subtractStrokes = [];
  currentStroke = [];
  selCanvas.classList.remove('drawing');
  selCtx.clearRect(0, 0, selCanvas.width, selCanvas.height);
  bboxContainer.style.pointerEvents = '';
  document.querySelectorAll('.bounding-box').forEach(b => b.style.pointerEvents = '');
  document.getElementById('btn-subtract-mode').style.display = 'none';
  btnDrawSelect.innerText  = '✏️ Draw Selection';
  btnDrawSelect.classList.remove('btn-primary');
  btnDrawSelect.classList.add('btn-secondary');
  btnDrawSelect.disabled = false;
}

// ── Subtract mode toggle button (injected into the toolbar) ─────────────────
(function injectSubtractBtn() {
  const btn = document.createElement('button');
  btn.id        = 'btn-subtract-mode';
  btn.className = 'btn btn-ghost';
  btn.title     = 'Hold/click to subtract from selection (punch holes)';
  btn.style.display = 'none';
  btn.style.fontSize = '0.82rem';
  btn.innerHTML = '➖ Subtract Region';
  btn.addEventListener('click', () => {
    drawSubtract = !drawSubtract;
    btn.innerHTML = drawSubtract ? '➕ Add Region' : '➖ Subtract Region';
    btn.style.background = drawSubtract ? 'rgba(239,68,68,0.18)' : '';
  });
  btnDrawSelect.parentElement.insertBefore(btn, btnDrawSelect);
})();

btnDrawSelect.addEventListener('click', () => {
  if (!drawMode) {
    resizeSelCanvas();
    enterDrawMode();
  } else {
    confirmDrawMode();
  }
});

// ── Drawing: click once to START a stroke, click again to COMMIT it ───────
// Window-level mousemove captures points even when cursor is outside canvas.
function makePoint(e) {
  const cr = selCanvas.getBoundingClientRect();
  const ir = imageWorkspace.getBoundingClientRect();
  return {
    x:  (e.clientX - cr.left) / cr.width  * selCanvas.width,
    y:  (e.clientY - cr.top)  / cr.height * selCanvas.height,
    // Allow coords outside [0,1] — backend clamps to image bounds
    fx: (e.clientX - ir.left) / ir.width,
    fy: (e.clientY - ir.top)  / ir.height,
  };
}

selCanvas.addEventListener('click', (e) => {
  if (!drawMode || e.button !== 0) return;
  e.stopPropagation();
  if (!isDrawing) {
    // First click → start new stroke
    isDrawing     = true;
    currentStroke = [makePoint(e)];
  } else {
    // Second click → commit stroke
    currentStroke.push(makePoint(e));
    if (currentStroke.length >= 3) {
      if (drawSubtract) subtractStrokes.push(currentStroke);
      else              addStrokes.push(currentStroke);
    }
    isDrawing     = false;
    currentStroke = [];
    redrawCanvas();
  }
});

// Track pointer globally while a stroke is active
window.addEventListener('mousemove', (e) => {
  if (!isDrawing || !drawMode) return;
  currentStroke.push(makePoint(e));
  redrawCanvas();
});

// Right-click: undo last committed stroke (or cancel in-progress)
selCanvas.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  if (isDrawing) {
    // Cancel current stroke
    isDrawing     = false;
    currentStroke = [];
    redrawCanvas();
  } else {
    if (drawSubtract) subtractStrokes.pop();
    else              addStrokes.pop();
    redrawCanvas();
  }
});

// Scroll on the canvas zooms normally — no stopPropagation.
