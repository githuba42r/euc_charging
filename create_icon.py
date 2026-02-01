import math
from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, filename, transparent=True):
    # Colors
    bg_color = (33, 150, 243)  # HA Blue
    text_color = (255, 255, 255)
    
    # Create image
    if transparent:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    else:
        img = Image.new('RGB', (size, size), (255, 255, 255))
        
    draw = ImageDraw.Draw(img)
    
    # Draw Circle
    margin = size * 0.05
    draw.ellipse([margin, margin, size-margin, size-margin], fill=bg_color)
    
    # Draw "EUC" text
    # Since we can't guarantee a font file, we'll draw simple shapes for EUC
    # or just a lightning bolt
    
    # Lightning bolt coordinates (normalized 0-1)
    points = [
        (0.55, 0.15),
        (0.35, 0.55),
        (0.50, 0.55),
        (0.45, 0.85),
        (0.65, 0.45),
        (0.50, 0.45)
    ]
    
    # Scale points
    scaled_points = [(x * size, y * size) for x, y in points]
    draw.polygon(scaled_points, fill=text_color)
    
    img.save(filename, 'PNG')

try:
    path = "custom_components/leaperkim_euc"
    if not os.path.exists(path):
        os.makedirs(path)
        
    create_icon(256, os.path.join(path, "icon.png"))
    create_icon(512, os.path.join(path, "logo.png"))
    print("Icons created successfully")
except Exception as e:
    print(f"Failed to create icon: {e}")
