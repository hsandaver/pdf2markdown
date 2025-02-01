import streamlit as st
import pdfplumber
from markdownify import markdownify as md
import pytesseract
from pdf2image import convert_from_path
import tempfile
import os
import re
from typing import Optional

# Set up the Streamlit page configuration
st.set_page_config(
    page_title="PDF to Markdown Converter",
    page_icon="📄➡️📑",
    layout="centered",
    initial_sidebar_state="auto",
)

# App title and description
st.title("📄 PDF to Markdown Converter")
st.markdown(
    """
    Convert your PDF documents to Markdown effortlessly. Perfect for preparing content for 
    Large Language Models (LLMs) or for seamless editing and sharing.
    """
)

# Sidebar options for configuration
st.sidebar.header("Options")
enable_ocr = st.sidebar.checkbox("Enable OCR (For Scanned PDFs)", value=False)
tesseract_cmd_path = st.sidebar.text_input("Tesseract Command Path (optional)")
show_logs = st.sidebar.checkbox("Show OCR Logs", value=True)
# Only show the DPI slider when OCR is enabled
ocr_dpi = st.sidebar.slider("OCR DPI", min_value=100, max_value=600, value=300, step=50) if enable_ocr else 300
# Option to split concatenated words (requires wordninja)
split_words = st.sidebar.checkbox("Split concatenated words", value=True)

def log_info(message: str) -> None:
    """Display log messages in the sidebar if logging is enabled, meep!"""
    if show_logs:
        st.sidebar.info(message)

def remove_page_headers(text: str) -> str:
    """
    Remove page headers/footers that match common patterns (e.g., "49/3 2024").
    """
    lines = text.splitlines()
    filtered_lines = []
    for line in lines:
        # If the line matches a header/footer pattern like "49/3 2024", skip it.
        if re.match(r'^\s*\d+/\d+\s+\d{4}\s*$', line):
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines)

def split_concatenated_words(text: str) -> str:
    """
    Use wordninja to attempt splitting words that were concatenated without spaces.
    (This may not be perfect, but it can help improve readability.)
    """
    try:
        import wordninja
    except ImportError:
        st.warning("wordninja is not installed; skipping concatenated word splitting.")
        return text

    # Split text into words and process each word individually.
    words = text.split()
    new_words = []
    for word in words:
        # If the word is long and might be a concatenation, try splitting it.
        if len(word) > 15:
            split_word = wordninja.split(word)
            # Only replace if the split version looks different.
            if len(split_word) > 1 and " ".join(split_word) != word:
                new_words.append(" ".join(split_word))
            else:
                new_words.append(word)
        else:
            new_words.append(word)
    return " ".join(new_words)

def clean_extracted_text(text: str) -> str:
    """
    Clean and reformat the extracted text to improve readability.

    This function:
      - Removes page headers/footers.
      - Fixes hyphenated line breaks (e.g. "exam-\nple" becomes "example").
      - Inserts missing spaces after punctuation.
      - Joins lines within a paragraph while preserving paragraph breaks.
      - Optionally splits concatenated words.
    """
    # Remove headers/footers first.
    text = remove_page_headers(text)
    # Fix hyphenated line breaks: "word-\nword" -> "wordword"
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    # Insert a space after a period if missing (e.g., "word.Another" -> "word. Another")
    text = re.sub(r'\.([A-Z])', r'. \1', text)
    # Split into paragraphs on two or more newlines.
    paragraphs = re.split(r'\n\s*\n', text)
    cleaned_paragraphs = []
    for para in paragraphs:
        # Replace newlines within paragraphs with a space and trim extra spaces.
        para = para.replace("\n", " ").strip()
        # Insert a space between a lowercase letter and an uppercase letter if needed.
        para = re.sub(r'([a-z])([A-Z])', r'\1 \2', para)
        cleaned_paragraphs.append(para)
    cleaned_text = "\n\n".join(cleaned_paragraphs)
    # Optionally split concatenated words.
    if split_words:
        cleaned_text = split_concatenated_words(cleaned_text)
    return cleaned_text

def extract_text_pdfplumber(pdf_file: str) -> str:
    """
    Extract text from a PDF using pdfplumber.
    
    Args:
        pdf_file (str): Path to the PDF file.
        
    Returns:
        str: Extracted text with page headings.
    """
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    text += f"\n\n# Page {page_num}\n\n{page_text}"
    except Exception as e:
        st.error(f"Error extracting text with pdfplumber: {e}")
    return text

def extract_text_ocr(pdf_file: str) -> str:
    """
    Extract text from a scanned PDF using OCR via pytesseract.
    
    Args:
        pdf_file (str): Path to the PDF file.
        
    Returns:
        str: Extracted text with page headings.
    """
    text = ""
    # Set a custom Tesseract command if provided.
    if tesseract_cmd_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd_path

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            images = convert_from_path(
                pdf_file, dpi=ocr_dpi, output_folder=temp_dir, fmt='png'
            )
        except Exception as e:
            st.error(f"Error converting PDF to images: {e}")
            return ""
        
        for i, image in enumerate(images):
            log_info(f"Performing OCR on page {i + 1}...")
            try:
                page_text = pytesseract.image_to_string(image)
            except Exception as ocr_error:
                st.error(f"OCR failed on page {i + 1}: {ocr_error}")
                continue
            text += f"\n\n# Page {i + 1}\n\n{page_text}"
    return text

def convert_to_markdown(text: str) -> str:
    """
    Convert raw text to Markdown format.
    
    Args:
        text (str): Raw text extracted from the PDF.
        
    Returns:
        str: Markdown formatted text.
    """
    markdown_text = md(text, heading_style="ATX")
    return markdown_text

def process_pdf(file_bytes: bytes) -> Optional[str]:
    """
    Process the uploaded PDF file and extract its text.
    
    Args:
        file_bytes (bytes): Byte content of the uploaded PDF.
        
    Returns:
        Optional[str]: The extracted text if successful, or None if not.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(file_bytes)
        tmp_filename = tmp_file.name

    try:
        if enable_ocr:
            log_info("Using OCR for text extraction.")
            extracted_text = extract_text_ocr(tmp_filename)
        else:
            log_info("Using pdfplumber for text extraction.")
            extracted_text = extract_text_pdfplumber(tmp_filename)
    finally:
        # Clean up the temporary file.
        if os.path.exists(tmp_filename):
            os.unlink(tmp_filename)

    return extracted_text if extracted_text.strip() else None

def main():
    """Main function to run the PDF to Markdown conversion app."""
    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    
    if uploaded_file is not None:
        with st.spinner("Processing your PDF..."):
            extracted_text = process_pdf(uploaded_file.read())
        
        if extracted_text:
            # Clean up the extracted text to improve formatting, nyah~
            cleaned_text = clean_extracted_text(extracted_text)
            markdown_text = convert_to_markdown(cleaned_text)
            
            with st.expander("Preview Markdown"):
                st.markdown(markdown_text)
                
            st.download_button(
                label="📥 Download Markdown",
                data=markdown_text,
                file_name="output.md",
                mime="text/markdown",
            )
        else:
            st.error("No text could be extracted from the PDF. It may be empty or an error occurred, nyah~.")
    else:
        st.info("Please upload a PDF file to begin the conversion.")

if __name__ == "__main__":
    main()
