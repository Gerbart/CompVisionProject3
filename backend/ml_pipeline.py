import os
import sys
import numpy as np
import base64
from PIL import Image
import cv2
import uuid

# Resolve project root from this file's location (backend/ml_pipeline.py -> project root)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRIPOSR_PATH = os.path.join(PROJECT_ROOT, "TripoSR")

# Furniture-focused text queries for OWL-ViT zero-shot detection
OWL_QUERIES = [[
    "a chair", "a couch", "a sofa", "a table", "a coffee table",
    "a dining table", "a side table", "a desk", "a bed", "a dresser",
    "a bookshelf", "a shelf", "a cabinet", "a tv stand", "a lamp",
    "an ottoman", "a bench", "a stool", "a nightstand", "a wardrobe"
]]


class CVProjectPipeline:
    def __init__(self):
        self.owl_processor = None
        self.owl_model = None
        self._load_owl()

    # ------------------------------------------------------------------ #
    #  Model loading                                                       #
    # ------------------------------------------------------------------ #
    def _load_owl(self):
        """Load OWL-ViT on CPU. Imported lazily to avoid torch-directml clash."""
        print("Loading OWL-ViT Zero-Shot Detector (CPU)...")
        # Deferred import so torch-directml's startup hook doesn't interfere
        import torch
        from transformers import OwlViTProcessor, OwlViTForObjectDetection

        self.torch = torch
        self.owl_processor = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
        self.owl_model = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")
        self.owl_model.eval()
        print("OWL-ViT Loaded.")

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    def _compute_iou(self, box1, box2):
        x1_max = min(box1[2], box2[2]); y1_max = min(box1[3], box2[3])
        x1_min = max(box1[0], box2[0]); y1_min = max(box1[1], box2[1])
        inter  = max(0, x1_max - x1_min) * max(0, y1_max - y1_min)
        a1     = (box1[2] - box1[0]) * (box1[3] - box1[1])
        a2     = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union  = float(a1 + a2 - inter)
        return inter / union if union > 0 else 0.0

    # ------------------------------------------------------------------ #
    #  Stage 1: Semantic Detection                                         #
    # ------------------------------------------------------------------ #
    def analyze_image(self, image_path: str):
        """
        OWL-ViT zero-shot detection → GrabCut segmentation.
        Returns objects sorted largest → smallest by bounding-box area.
        """
        img_cv2 = cv2.imread(image_path)
        img_pil = Image.open(image_path).convert("RGB")
        W, H   = img_pil.size

        with self.torch.no_grad():
            inputs = self.owl_processor(
                text=OWL_QUERIES, images=img_pil, return_tensors="pt"
            )
            outputs = self.owl_model(**inputs)
            target_sizes = self.torch.tensor([(H, W)])
            results = self.owl_processor.post_process_object_detection(
                outputs, threshold=0.1, target_sizes=target_sizes
            )[0]

        raw_boxes  = results["boxes"].cpu().numpy()
        raw_scores = results["scores"].cpu().numpy()
        raw_labels = results["labels"].cpu().numpy()

        # Score-ordered NMS with IoU threshold
        order = np.argsort(-raw_scores)
        keep  = []
        for i in order:
            if all(self._compute_iou(raw_boxes[i], raw_boxes[j]) < 0.5 for j in keep):
                keep.append(i)

        objects = []
        for i in keep:
            x_min, y_min, x_max, y_max = raw_boxes[i].astype(int)
            x_min = max(0, x_min); y_min = max(0, y_min)
            x_max = min(W - 1, x_max); y_max = min(H - 1, y_max)

            w = x_max - x_min; h = y_max - y_min
            area = w * h
            if area < 500 or area > W * H * 0.9 or w < 2 or h < 2:
                continue

            # Map label index → text
            idx = int(raw_labels[i])
            raw_label = OWL_QUERIES[0][idx] if idx < len(OWL_QUERIES[0]) else "object"
            label = raw_label.replace("a ", "").replace("an ", "").strip()

            # GrabCut segmentation
            mask = np.zeros(img_cv2.shape[:2], np.uint8)
            bgd  = np.zeros((1, 65), np.float64)
            fgd  = np.zeros((1, 65), np.float64)
            try:
                cv2.grabCut(img_cv2, mask, (int(x_min), int(y_min), int(w), int(h)),
                            bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
            except cv2.error:
                continue

            final_mask = np.where((mask == 2) | (mask == 0), 0, 255).astype(np.uint8)

            # Transparent cutout for sidebar
            rgba = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2BGRA)
            rgba[:, :, 3] = final_mask
            cutout = rgba[y_min:y_max, x_min:x_max]

            _, buf = cv2.imencode('.png', cutout)
            b64 = base64.b64encode(buf).decode('utf-8')

            mask_id   = f"mask_{uuid.uuid4().hex[:8]}.png"
            mask_path = os.path.join("temp", mask_id)
            cv2.imwrite(mask_path, final_mask)

            objects.append({
                "id":         uuid.uuid4().hex[:8],
                "label":      label,
                "box":        [int(x_min), int(y_min), int(w), int(h)],
                "_area":      area,
                "mask_id":    mask_id,
                "cutout_b64": f"data:image/png;base64,{b64}",
            })

            if len(objects) >= 20:
                break

        # Sort by area descending, then strip internal field
        objects.sort(key=lambda o: o["_area"], reverse=True)
        for o in objects:
            del o["_area"]

        return objects

    # ------------------------------------------------------------------ #
    #  Stage 2: Object Removal / Inpainting                               #
    # ------------------------------------------------------------------ #
    def remove_object(self, image_path: str, mask_path: str,
                      num_options: int = 3, use_ai: bool = False):
        img  = cv2.imread(image_path)
        mask = cv2.imread(mask_path, 0)

        # Dilate mask to cover edge fringe
        kernel       = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
        mask_dilated = cv2.dilate(mask, kernel, iterations=1)

        if use_ai:
            try:
                ai_cv = self._ai_remove(img, mask_dilated)
                paths = []
                # Return AI result first, then two OpenCV variants for comparison
                p = os.path.join("temp", f"ai_{uuid.uuid4().hex[:8]}.png")
                cv2.imwrite(p, ai_cv)
                paths.append(p)
                for r in [cv2.inpaint(img, mask_dilated, 5, cv2.INPAINT_NS),
                           cv2.inpaint(img, mask_dilated, 10, cv2.INPAINT_TELEA)]:
                    p = os.path.join("temp", f"inpainted_{uuid.uuid4().hex[:8]}.png")
                    cv2.imwrite(p, r)
                    paths.append(p)
                return paths
            except Exception as e:
                print(f"AI inpainting failed: {e} -- falling back to OpenCV.")

        # --- Structure-aware OpenCV inpainting (3 variants with dilated mask) ---
        r1 = cv2.inpaint(img, mask_dilated, 5,  cv2.INPAINT_NS)
        r2 = cv2.inpaint(img, mask_dilated, 4,  cv2.INPAINT_TELEA)
        r3 = cv2.inpaint(img, mask_dilated, 12, cv2.INPAINT_TELEA)

        paths = []
        for res in [r1, r2, r3]:
            p = os.path.join("temp", f"inpainted_{uuid.uuid4().hex[:8]}.png")
            cv2.imwrite(p, res)
            paths.append(p)
        return paths

    # ------------------------------------------------------------------ #
    #  AI Removal Helpers                                                  #
    # ------------------------------------------------------------------ #
    def _ai_remove(self, img_cv: np.ndarray, mask_cv: np.ndarray) -> np.ndarray:
        """
        Two-pass reference-anchored inpainting:
          Pass 1  OpenCV Navier-Stokes  =>  background hypothesis (no hallucination)
          Pass 2  SD inpainting @ strength=0.30 anchored to Pass-1 result
                  => texture clean-up WITHOUT inventing new objects
        The low denoising strength is the key: SD barely deviates from the
        Pass-1 hint, so it CAN'T conjure new furniture/objects.
        """
        import torch
        from diffusers import StableDiffusionInpaintPipeline

        H, W = img_cv.shape[:2]

        # ----- Pass 1: OpenCV background hypothesis -----
        hint_cv = cv2.inpaint(img_cv, mask_cv, 8, cv2.INPAINT_NS)

        # ----- Analyse surrounding context for the SD prompt -----
        prompt     = self._bg_context_prompt(img_cv, mask_cv)
        neg_prompt = (
            "furniture, chair, table, sofa, couch, desk, lamp, shelf, plant, "
            "book, decoration, object, item, person, any placed object, anything new"
        )
        print(f"AI removal: prompt='{prompt}'")

        # ----- Load / cache SD pipeline -----
        if not hasattr(self, '_sd_pipe') or self._sd_pipe is None:
            print("Loading SD Inpainting model (first load, ~1 min)...")
            self._sd_pipe = StableDiffusionInpaintPipeline.from_pretrained(
                "runwayml/stable-diffusion-inpainting",
                torch_dtype=torch.float32,
                safety_checker=None,
            ).to("cpu")
            self._sd_pipe.set_progress_bar_config(disable=True)
            print("SD model ready.")

        # Resize to 512×512 (SD's native resolution)
        hint_pil = Image.fromarray(cv2.cvtColor(hint_cv, cv2.COLOR_BGR2RGB))
        mask_pil = Image.fromarray(mask_cv).convert("L")
        h512 = hint_pil.resize((512, 512), Image.LANCZOS)
        m512 = mask_pil.resize((512, 512), Image.NEAREST)

        # ----- Pass 2: SD with ultra-low strength -----
        with torch.no_grad():
            out = self._sd_pipe(
                prompt          = prompt,
                negative_prompt = neg_prompt,
                image           = h512,
                mask_image      = m512,
                strength        = 0.30,   # conservative: SD barely changes the hint
                guidance_scale  = 5.0,    # low: less creative, fewer hallucinations
                num_inference_steps = 25,
            ).images[0]

        # Resize back to original resolution
        result_pil = out.resize((W, H), Image.LANCZOS)
        result_cv  = cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)

        # ----- Poisson blending: seamlessly fuse result into original -----
        ys, xs = np.where(mask_cv > 0)
        if len(ys) > 0:
            cx = int((int(xs.min()) + int(xs.max())) / 2)
            cy = int((int(ys.min()) + int(ys.max())) / 2)
            try:
                result_cv = cv2.seamlessClone(
                    result_cv, img_cv, mask_cv, (cx, cy), cv2.NORMAL_CLONE
                )
            except cv2.error:
                pass  # if Poisson fails, just return the raw SD output

        return result_cv

    def _bg_context_prompt(self, img_cv: np.ndarray, mask_cv: np.ndarray) -> str:
        """
        Sample pixels in a band just OUTSIDE the mask to classify background type
        and return a targeted inpainting prompt.
        """
        k_big   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
        k_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,  5))
        border  = cv2.subtract(cv2.dilate(mask_cv, k_big), cv2.dilate(mask_cv, k_small))

        ys, xs = np.where(border > 0)
        if len(ys) == 0:
            return "seamless background, empty clean surface"

        px  = img_cv[ys, xs].astype(float)          # BGR
        mb, mg, mr = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
        brightness  = mr * 0.299 + mg * 0.587 + mb * 0.114
        sat = (max(mr, mg, mb) - min(mr, mg, mb)) / (max(mr, mg, mb) + 1e-6)

        if brightness > 200:
            return "seamless white surface, empty white background"
        if brightness > 155:
            if sat < 0.15:
                return "light grey smooth surface, neutral empty floor"
            return "light wood texture, empty wooden surface, hardwood floor"
        if brightness > 100:
            if sat < 0.15:
                return "grey floor, neutral concrete surface, empty grey background"
            if mr > mg and mr > mb:
                return "warm hardwood floor, empty wood surface, seamless wood texture"
            if mg > mr:
                return "carpet, seamless green carpet, empty carpeted floor"
            return "tile floor, seamless tile surface, empty floor"
        if brightness > 60:
            return "dark wood surface, empty dark wooden floor, seamless dark wood"
        return "dark surface, empty dark background, seamless dark floor"

    # ------------------------------------------------------------------ #
    #  Stage 3: 3D Generation via TripoSR + DirectML                      #
    # ------------------------------------------------------------------ #
    def generate_3d_model(self, image_path: str, mask_path: str):
        """
        Isolates the masked object → runs TripoSR on AMD DirectML → exports .glb.
        Both temp/ (served via API) and outputs/ (permanent) copies are saved.
        """
        # --- Isolate object from full image using mask ---
        img_cv  = cv2.imread(image_path)
        mask_cv = cv2.imread(mask_path, 0)

        # -- Tight crop: only the object pixels, nothing surrounding --
        # Erode the mask slightly to shed shadow pixels at edges
        k_erode  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        mask_tight = cv2.erode(mask_cv, k_erode, iterations=2)

        # Apply tight mask as alpha channel
        rgba_tight    = cv2.cvtColor(img_cv, cv2.COLOR_BGR2BGRA)
        rgba_tight[:, :, 3] = mask_tight

        # Find bounding box of the tight mask
        y_idx, x_idx = np.where(mask_tight > 0)
        if len(y_idx) == 0:
            # Fall back to original mask if erosion removed everything
            y_idx, x_idx = np.where(mask_cv > 0)
            rgba_tight[:, :, 3] = mask_cv

        x1, x2 = int(np.min(x_idx)), int(np.max(x_idx))
        y1, y2 = int(np.min(y_idx)), int(np.max(y_idx))

        # Add a 15% margin around the object so TripoSR doesn't see a flush-edge crop.
        # Without margin, square objects hit the image border and confuse the generator.
        H_img, W_img = rgba_tight.shape[:2]
        pad_x = max(20, int((x2 - x1) * 0.15))
        pad_y = max(20, int((y2 - y1) * 0.15))
        x1m = max(0, x1 - pad_x)
        y1m = max(0, y1 - pad_y)
        x2m = min(W_img - 1, x2 + pad_x)
        y2m = min(H_img - 1, y2 + pad_y)
        rgba_cropped = rgba_tight[y1m:y2m+1, x1m:x2m+1]

        proc_path = os.path.join("temp", f"tripo_input_{uuid.uuid4().hex[:8]}.png")
        cv2.imwrite(proc_path, rgba_cropped)

        # --- TripoSR import (uses __file__-relative path, immune to CWD) ---
        if TRIPOSR_PATH not in sys.path:
            sys.path.insert(0, TRIPOSR_PATH)

        try:
            import torch
            import torch_directml
            from tsr.system import TSR
        except ModuleNotFoundError as exc:
            raise ImportError(
                f"TripoSR import error: {exc}\n"
                f"Looked in: {TRIPOSR_PATH}\n"
                "Ensure the TripoSR folder is at the project root."
            )

        print("Initialising TripoSR on AMD DirectML…")
        dml = torch_directml.device()

        model = TSR.from_pretrained(
            "stabilityai/TripoSR",
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        model.renderer.set_chunk_size(8192)
        model.to(dml)
        model.eval()

        # TripoSR expects a square RGB image (512x512, clean solid background).
        rgba_img = Image.open(proc_path).convert("RGBA")

        # 1. Composite onto pure white (white is universally best for TripoSR)
        bg      = Image.new("RGBA", rgba_img.size, (255, 255, 255, 255))
        composed = Image.alpha_composite(bg, rgba_img).convert("RGB")

        # 2. Pad to square (letterbox) so the object isn't distorted
        W_img, H_img = composed.size
        side   = max(W_img, H_img)
        # Add 20% whitespace margin so objects don't hit the image border
        margin = max(24, int(side * 0.20))
        side  += margin * 2
        square = Image.new("RGB", (side, side), (255, 255, 255))
        square.paste(composed, ((side - W_img) // 2, (side - H_img) // 2))

        # 3. Resize to 512x512 (TripoSR's standard conditioning size)
        image = square.resize((512, 512), Image.LANCZOS)
        print("Generating mesh...")
        with torch.no_grad():
            codes  = model([image], device=dml)
            meshes = model.extract_mesh(codes, has_vertex_color=True, resolution=256)
            mesh   = meshes[0]

        filename  = f"model_{uuid.uuid4().hex[:8]}.glb"
        temp_path = os.path.join("temp", filename)
        out_dir   = os.path.join(PROJECT_ROOT, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        out_path  = os.path.join(out_dir, filename)

        mesh.export(temp_path)
        # Reload the exported mesh with trimesh so we can apply the rotation cleanly
        import trimesh as tm
        loaded = tm.load(temp_path)
        # Rotate -90 deg around X axis so the object sits upright in viewers / Blender
        rot = tm.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
        loaded.apply_transform(rot)
        loaded.export(temp_path)

        import shutil
        shutil.copyfile(temp_path, out_path)

        print("Saved -> " + out_path)
        return temp_path


pipeline = CVProjectPipeline()
