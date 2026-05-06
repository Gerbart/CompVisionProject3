import sys
import os
sys.path.append('backend')
from ml_pipeline import pipeline

# Create a dummy transparent image
import cv2
import numpy as np
img = np.zeros((100, 100, 3), dtype=np.uint8)
img[:] = (255, 0, 0)
cv2.imwrite('temp/dummy_img.png', img)

mask = np.zeros((100, 100), dtype=np.uint8)
mask[25:75, 25:75] = 255
cv2.imwrite('temp/dummy_mask.png', mask)

print("Starting generation...")
try:
    res = pipeline.generate_3d_model('temp/dummy_img.png', 'temp/dummy_mask.png')
    print("Success:", res)
except Exception as e:
    import traceback
    traceback.print_exc()
