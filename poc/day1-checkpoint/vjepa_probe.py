import glob

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoVideoProcessor

MODEL_ID = "facebook/vjepa2-vitl-fpc64-256"

processor = AutoVideoProcessor.from_pretrained(MODEL_ID)
model = AutoModel.from_pretrained(MODEL_ID, dtype=torch.float32)
model.eval()

frame_paths = sorted(glob.glob("frames_64/frame_*.jpg"))[:64]
frames = np.stack([np.array(Image.open(p).convert("RGB")) for p in frame_paths])  # T x H x W x C
video = torch.from_numpy(frames).permute(0, 3, 1, 2)  # T x C x H x W

inputs = processor(video, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs)

encoder_out = outputs.last_hidden_state
predictor_out = outputs.predictor_output.last_hidden_state

print(f"frames used: {len(frame_paths)}")
print(f"encoder output shape: {tuple(encoder_out.shape)}")
print(f"predictor output shape: {tuple(predictor_out.shape)}")
print(f"encoder output mean/std: {encoder_out.mean().item():.4f} / {encoder_out.std().item():.4f}")
