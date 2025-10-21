import torch
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image

# Load BLIP model and processor once (global)
processor = None
model = None

def load_blip_model():
    """Load BLIP model and return the model instance (for shared use)."""
    global processor, model
    if processor is None or model is None:
        processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
        model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
        
        # Move to GPU if available
        if torch.cuda.is_available():
            model = model.cuda()
        model.eval()
    return model

def get_blip_caption(pil_image):
    """Single image caption (legacy API)."""
    load_blip_model()
    inputs = processor(pil_image, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.cuda() for k, v in inputs.items()}
    with torch.no_grad():
        out = model.generate(**inputs)
    caption = processor.decode(out[0], skip_special_tokens=True)
    return caption

def get_blip_caption_with_model(model_instance, pil_image):
    """Single image caption using pre-loaded model (avoids reload)."""
    global processor
    if processor is None:
        load_blip_model()
    inputs = processor(pil_image, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.cuda() for k, v in inputs.items()}
    with torch.no_grad():
        out = model_instance.generate(**inputs)
    caption = processor.decode(out[0], skip_special_tokens=True)
    return caption

def batch_blip_captions(model_instance, pil_images, batch_size=8):
    """Batch image caption generation (GPU-optimized).
    
    Args:
        model_instance: Pre-loaded BLIP model
        pil_images: list of PIL Images
        batch_size: number of images to process together on GPU
    
    Returns:
        list of caption strings (same length as pil_images)
    """
    global processor
    if processor is None:
        load_blip_model()
    
    captions = []
    for i in range(0, len(pil_images), batch_size):
        batch = pil_images[i:i+batch_size]
        inputs = processor(batch, return_tensors="pt", padding=True)
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}
        
        with torch.no_grad():
            outs = model_instance.generate(**inputs)
        
        for out in outs:
            caption = processor.decode(out, skip_special_tokens=True)
            captions.append(caption)
    
    return captions
