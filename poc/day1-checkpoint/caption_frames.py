import glob

from mlx_vlm import load, generate
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import load_config

MODEL_PATH = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
PROMPT = "Bu görüntüde ne oluyor? Tek cümlede, Türkçe olarak kısaca açıkla."

model, processor = load(MODEL_PATH)
config = load_config(MODEL_PATH)

frame_paths = sorted(glob.glob("frames/frame_*.jpg"))
formatted_prompt = apply_chat_template(processor, config, PROMPT, num_images=1)

for i, path in enumerate(frame_paths):
    output = generate(
        model,
        processor,
        formatted_prompt,
        [path],
        max_tokens=80,
        temperature=0.3,
        repetition_penalty=1.3,
        repetition_context_size=40,
        verbose=False,
    )
    text = getattr(output, "text", output)
    print(f"[t={i}s] {path}: {str(text).strip()}")
