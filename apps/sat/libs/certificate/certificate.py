import fitz  
import os
import tempfile
from django.core.files.base import ContentFile
from apps.sat.storages import PrivateStorage
from django.conf import settings



def create_certificate(replacements, code, path, black_counts):
    base = path / 'apps/sat/libs/certificate'
    doc = fitz.open(base / 'template_dsat.pdf')
    BLACK_IMG = base / "black.jpg"
    WHITE_IMG = base / "white.jpg"
    
    # Use private storage for certificates (requires signed URLs)
    storage = PrivateStorage()
    page = doc[0]

    for text_to_replace, replacement in replacements.items():

        text_instances = page.search_for(text_to_replace)
        for inst in text_instances:

            page.add_redact_annot(inst, fill=(1, 1, 1))  
            page.apply_redactions()

        
        for inst in text_instances:
            x, y, _, _ = inst
            if text_to_replace in ["full_name", "test_name", "test_date"]:
                page.insert_text((x, y+10), replacement, fontsize=10, fontfile=base/"ttf/Arial-Black.ttf", color=(0, 0, 0))  # Bold, black text for specific placeholders
            elif text_to_replace == "t-sc":
                page.insert_text((x, y+20), replacement, fontsize=21, fontfile=base/"ttf/DejaVuSans-Bold.ttf", color=(0, 0, 0))
            elif text_to_replace in ["t-rs", "r-rs", "m-rs"]:
                page.insert_text((x, y+5), replacement, fontsize=5, fontfile=base/"ttf/DejaVuSans.ttf", color=(0, 0, 0))
            elif text_to_replace in ["r-sc", "m-sc"]:
                page.insert_text((x, y+12), replacement, fontsize=12, fontfile=base/"ttf/DejaVuSans.ttf", color=(0, 0, 0))
            else:
                page.insert_text((x, y+10), replacement, fontsize=10, fontfile=base/"ttf/DejaVuSans.ttf", color=(0, 0, 0))


    x_starts = [171.553, 372.585]  
    y_coordinates = [
    269.518,  # Row 1
    304.612,  # Row 2
    339.706,  # Row 3
    374.796,  # Row 4
    269.518,  # Row 1
    304.612,  # Row 2
    339.706,  # Row 3
    374.796   # Row 4
    ]
    box_width = 26.135
    gap = 0.908  
    box_height = 5.639

    for row_index, (black_count, current_y) in enumerate(zip(black_counts, y_coordinates)):
        current_x_start = x_starts[0] if row_index < 4 else x_starts[1]
        for col_index in range(7):  
            current_x = current_x_start + col_index * (box_width + gap)
            rect = fitz.Rect(current_x, current_y, current_x + box_width, current_y + box_height)
            if col_index < black_count:
                page.insert_image(rect, filename=BLACK_IMG)
            else:
                page.insert_image(rect, filename=WHITE_IMG)
    # Create a temporary file to save the PDF
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
        doc.save(temp_file.name)
        
        # Read the PDF content
        with open(temp_file.name, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
        
        # Upload to R2 storage
        file_name = f'certificates/{code}.pdf'
        certificate_file = ContentFile(pdf_content, name=file_name)
        
        # Save to R2 and get the URL
        file_path = storage.save(file_name, certificate_file)
        
        # Clean up temporary file
        os.unlink(temp_file.name)
        
        # Return the R2 file path (not URL, we'll generate URL when needed)
        return file_path


# black_counts = [
#     3,  
#     5,  
#     2,  
#     4,  
#     1,        
#     6,  
#     0,  
#     7
# ]

# detials = {
#     "t-sc": "1380",
#     "t-rs": "1340-1420",
#     "full_name": "Asilbek-Ziyod Qilichev",
#     "test_name": "DAY32",
#     "test_date": "October 5, 2024",
#     "r-sc": "680",
#     "r-rs": "650-710",
#     "m-sc": "700",
#     "m-rs": "670-730"
# }

