import base64
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid
import shutil
from PIL import Image
import numpy as np
import cv2
from fastapi.staticfiles import StaticFiles

from ml_pipeline import pipeline

app = FastAPI(title="ShapeShift API - CV Project 3")

# Mount temp directory to serve 3D models statically
app.mount("/api/temp", StaticFiles(directory="temp"), name="temp")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("temp", exist_ok=True)

class AnalyzeRequest(BaseModel):
    image_id: str

class InpaintRequest(BaseModel):
    image_id: str
    mask_id: str
    num_options: int = 3
    use_ai: bool = False

class Generate3DRequest(BaseModel):
    image_id: str
    mask_id: str

class GenerateRequest(BaseModel):
    image_id: str
    mask_id: str
    prompt: str

class SmartMaskRequest(BaseModel):
    image_id: str
    base_mask_id: Optional[str] = None
    points: list = []           # legacy single-stroke (first add stroke)
    add_strokes: list = []      # list of strokes, each stroke = [[x_frac, y_frac], ...]
    subtract_strokes: list = [] # strokes to subtract (punch holes)

def save_base64_image(b64_str: str, prefix: str = "img"):
    if "," in b64_str:
        b64_str = b64_str.split(",")[1]
    img_data = base64.b64decode(b64_str)
    file_id = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join("temp", file_id)
    with open(file_path, "wb") as f:
        f.write(img_data)
    return file_id, file_path

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    file_id = f"img_{uuid.uuid4().hex[:8]}.png"
    file_path = os.path.join("temp", file_id)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"status": "success", "image_id": file_id}

@app.post("/api/analyze")
async def analyze_image(request: AnalyzeRequest):
    img_path = os.path.join("temp", request.image_id)
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")
        
    objects = pipeline.analyze_image(img_path)
    return {"status": "success", "objects": objects}

@app.post("/api/inpaint")
async def inpaint_object(request: InpaintRequest):
    img_path = os.path.join("temp", request.image_id)
    mask_path = os.path.join("temp", request.mask_id)
    
    result_urls = pipeline.remove_object(img_path, mask_path, request.num_options, request.use_ai)
    
    # Return as base64 so frontend can show it immediately
    b64_options = []
    for path in result_urls:
        if path.startswith("/"):
            b64_options.append(path) # Demo paths
            continue
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
            b64_options.append(f"data:image/png;base64,{b64}")
            
    return {"status": "success", "options": b64_options}

@app.post("/api/generate_3d")
async def generate_3d(request: Generate3DRequest):
    img_path = os.path.join("temp", request.image_id)
    mask_path = os.path.join("temp", request.mask_id)
    
    out_path, tripo_in_path = pipeline.generate_3d_model(img_path, mask_path)
    
    # Return the URL path to the generated model and input image
    model_url = f"http://localhost:8000/api/temp/{os.path.basename(out_path)}"
    tripo_url = f"http://localhost:8000/api/temp/{os.path.basename(tripo_in_path)}"
    
    return {"status": "success", "model_url": model_url, "tripo_url": tripo_url}

@app.post("/api/generate")
async def generate_fill(request: GenerateRequest):
    img_path  = os.path.join("temp", request.image_id)
    mask_path = os.path.join("temp", request.mask_id)
    if not os.path.exists(img_path) or not os.path.exists(mask_path):
        raise HTTPException(status_code=404, detail="Image or mask not found")
    out_path = pipeline.generate_over_mask(img_path, mask_path, request.prompt)
    with open(out_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    return {"status": "success", "result_b64": f"data:image/png;base64,{b64}", "image_id": os.path.basename(out_path)}

@app.post("/api/smart_mask")
async def smart_mask(request: SmartMaskRequest):
    """
    Paints user-drawn strokes directly onto a mask — no GrabCut, no dilation.
    Add strokes fill pixels white; subtract strokes punch holes (black).
    If base_mask_id is supplied the existing mask is used as the starting point.
    Returns the exact pixel mask the user drew.
    """
    img_path = os.path.join("temp", request.image_id)
    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    img = cv2.imread(img_path)
    if img is None:
        raise HTTPException(status_code=500, detail="Could not read image")
    H, W = img.shape[:2]

    def frac_stroke_to_pixels(stroke):
        return np.array(
            [[int(np.clip(pt[0], 0.0, 1.0) * (W - 1)),
              int(np.clip(pt[1], 0.0, 1.0) * (H - 1))]
             for pt in stroke],
            dtype=np.int32
        )

    raw_add = request.add_strokes if request.add_strokes else ([request.points] if len(request.points) >= 3 else [])
    raw_sub = request.subtract_strokes

    if not raw_add and not request.base_mask_id:
        raise HTTPException(status_code=400, detail="Need at least one add stroke or a base mask")

    # Start from the existing mask (for edits) or a blank canvas
    poly_mask = np.zeros((H, W), dtype=np.uint8)
    if request.base_mask_id:
        base_mask_path = os.path.join("temp", request.base_mask_id)
        if os.path.exists(base_mask_path):
            base_mask = cv2.imread(base_mask_path, cv2.IMREAD_GRAYSCALE)
            if base_mask is not None and base_mask.shape == (H, W):
                poly_mask = base_mask.copy()

    # Paint add strokes (union)
    for stroke in raw_add:
        if len(stroke) < 3:
            continue
        px = frac_stroke_to_pixels(stroke)
        cv2.fillPoly(poly_mask, [px.reshape(-1, 1, 2)], 255)

    # Paint subtract strokes (punch holes)
    for stroke in raw_sub:
        if len(stroke) < 3:
            continue
        px = frac_stroke_to_pixels(stroke)
        cv2.fillPoly(poly_mask, [px.reshape(-1, 1, 2)], 0)

    ys, xs = np.where(poly_mask > 0)
    if len(ys) == 0:
        raise HTTPException(status_code=400, detail="Selection area is empty after all strokes")

    # Bounding box of the non-zero region (no padding — exact pixels only)
    x1, y1 = int(xs.min()), int(ys.min())
    x2, y2 = int(xs.max()), int(ys.max())

    # Save the mask — same file served as both "gc" and "poly" (they're identical here)
    mask_id = f"smart_{uuid.uuid4().hex[:8]}.png"
    cv2.imwrite(os.path.join("temp", mask_id), poly_mask)
    _, mbuf  = cv2.imencode('.png', poly_mask)
    mask_b64 = base64.b64encode(mbuf).decode('utf-8')
    mask_b64_uri = f"data:image/png;base64,{mask_b64}"

    return {
        "status":        "success",
        "box":           [x1, y1, x2 - x1, y2 - y1],
        # GrabCut-refined field (now identical to raw — no GrabCut)
        "mask_id":       mask_id,
        "mask_b64":      mask_b64_uri,
        # Raw polygon field
        "poly_mask_id":  mask_id,
        "poly_mask_b64": mask_b64_uri,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
