"""
Standalone TripoSR test - runs on CPU (torchmcubes requires CPU tensors).
Feed the public/demo_3d.png image through the full pipeline and save the .glb.
Run from project root: dml_env\Scripts\python.exe test_triposr.py
"""
import sys
import os

# Add TripoSR to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "TripoSR"))

import torch
from PIL import Image

print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print("Note: TripoSR will run on CPU (torchmcubes requires CPU tensors)")

import torch_directml
dml = torch_directml.device()
print(f"DirectML available: {torch_directml.is_available()}")

from tsr.system import TSR

print("\nLoading TripoSR model from HuggingFace (or cache)...")
model = TSR.from_pretrained(
    "stabilityai/TripoSR",
    config_name="config.yaml",
    weight_name="model.ckpt",
)
model.to(dml)
model.eval()
print("Model loaded.")

# Use the demo image - a clean couch render
test_img_path = os.path.join("public", "demo_3d.png")
if not os.path.exists(test_img_path):
    # Create a minimal white test image if demo doesn't exist
    print(f"Warning: {test_img_path} not found, creating 512x512 white test image")
    test_img = Image.new("RGB", (512, 512), (255, 255, 255))
    os.makedirs("public", exist_ok=True)
    test_img.save(test_img_path)

# Prepare image: square pad + resize to 512x512 + RGB (exactly what TripoSR expects)
raw = Image.open(test_img_path).convert("RGBA")
white_bg = Image.new("RGBA", raw.size, (255, 255, 255, 255))
composed = Image.alpha_composite(white_bg, raw).convert("RGB")
W, H = composed.size
side = max(W, H)
square = Image.new("RGB", (side, side), (255, 255, 255))
square.paste(composed, ((side - W) // 2, (side - H) // 2))
image = square.resize((512, 512), Image.LANCZOS)
image.save("temp/triposr_test_input.png")
print(f"\nInput image prepared: {image.size}, mode={image.mode}")

print("\nRunning TripoSR forward pass...")
with torch.no_grad():
    codes = model([image], device=dml)
    print(f"Scene codes shape: {codes.shape}")

print("\nExtracting mesh (marching cubes)...")
with torch.no_grad():
    model.renderer.set_chunk_size(8192)
    meshes = model.extract_mesh(codes, has_vertex_color=False, resolution=256)
    mesh = meshes[0]

print(f"\nMesh extracted: {type(mesh)}")

os.makedirs("outputs", exist_ok=True)
out_path = "outputs/test_triposr.glb"
mesh.export(out_path)
print(f"\nSUCCESS! Model saved to: {out_path}")
print(f"File size: {os.path.getsize(out_path) / 1024:.1f} KB")
