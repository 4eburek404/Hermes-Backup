# Vision Fallback with Tesseract OCR

When a model doesn't support image inputs (e.g., `openai.BadRequestError` or `vision_analyze` returns failure), use local OCR to extract text from images.

## Setup
```bash
sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-rus
pip install pytesseract
```

## Recipe
Use this Python snippet to get high-confidence text and bounding boxes:

```python
import pytesseract
from PIL import Image

img_path = "/path/to/image.jpg"
img = Image.open(img_path)

# 1. Simple text extraction
text = pytesseract.image_to_string(img, lang="rus+eng")
print(text)

# 2. Detailed data for layout analysis
data = pytesseract.image_to_data(img, lang="rus+eng", output_type=pytesseract.Output.DICT)
for i in range(len(data["text"])):
    if data["text"][i].strip():
        print(f"[{data['left'][i]},{data['top'][i]}] {data['text'][i]}")
```

## Pitfalls
- **Language:** Always include `lang="rus+eng"` for Konstantin's environment.
- **Image Quality:** For small text, use `PIL.ImageEnhance.Contrast` to boost contrast before OCR.
- **Model Support:** Check `agent/models_dev.py` or `hermes config` to see if a model *should* support vision before falling back.
