import fitz  # PyMuPDF

def analyze_fonts_in_pdf(input_pdf_path):
    # Open the PDF
    doc = fitz.open(input_pdf_path)
    
    # Create a dictionary to hold font information for placeholders
    fonts_info = {}

    # Iterate through each page
    for page_number, page in enumerate(doc):
        # Extract text and font details
        text_blocks = page.get_text("dict")["blocks"]
        
        for block in text_blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Extract text and font details
                        text = span["text"]
                        font_name = span["font"]
                        font_size = span["size"]

                        # Check if the text matches one of the placeholders
                        placeholders = ["full_name", "test_name", "test_date", "t-sc", "t-rs", "r-sc", "r-rs", "m-sc", "m-rs"]
                        for placeholder in placeholders:
                            if placeholder in text:
                                # Store font information
                                fonts_info[placeholder] = {
                                    "font_name": font_name,
                                    "font_size": font_size,
                                    "page_number": page_number + 1  # Pages are zero-indexed
                                }
    
    # Print out the font information for each placeholder
    for placeholder, info in fonts_info.items():
        print(f"Placeholder: {placeholder}")
        print(f"  Font Name: {info['font_name']}")
        print(f"  Font Size: {info['font_size']}")
        print(f"  Page Number: {info['page_number']}\n")

# Call the function to analyze fonts in the PDF
analyze_fonts_in_pdf("template_dsat.pdf")
