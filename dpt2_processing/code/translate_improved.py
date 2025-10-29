#!/usr/bin/env python3
"""
Improved DPT-2 Translation Script - Line by Line Approach
Translates each paragraph individually for better reliability
"""

import os
import re
from pathlib import Path
from googletrans import Translator
import time
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Translation settings
TRANSLATION_DELAY = 1.0
MAX_RETRIES = 3

def detect_language_from_text(text):
    """Detect if text contains Indic script characters."""
    # Remove numbers and punctuation for detection
    text_for_detection = re.sub(r'[0-9\.\|\-\s\(\)]+', '', text)
    
    if not text_for_detection:
        return 'en'  # Only numbers/punctuation
    
    devanagari_pattern = re.compile(r'[\u0900-\u097F]')
    telugu_pattern = re.compile(r'[\u0C00-\u0C7F]')
    
    if devanagari_pattern.search(text_for_detection):
        return 'hi'
    elif telugu_pattern.search(text_for_detection):
        return 'te'
    else:
        return 'en'

def translate_line(text, translator):
    """Translate a single line/paragraph with retry logic."""
    if not text or not text.strip():
        return text
    
    # Check if already in English
    if detect_language_from_text(text) == 'en':
        return text
    
    for attempt in range(MAX_RETRIES):
        try:
            result = translator.translate(text, src='auto', dest='en')
            if result and hasattr(result, 'text') and result.text:
                time.sleep(TRANSLATION_DELAY)
                return result.text
            else:
                logger.warning(f"Translation returned None for: {text[:50]}...")
                return text
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                time.sleep(TRANSLATION_DELAY * 2)
                translator = Translator()  # New instance
            else:
                logger.error(f"All attempts failed for: {text[:50]}...")
                return text  # Return original
    
    return text

def clean_html_tags(content):
    """Remove HTML tags and convert tables to markdown."""
    # Remove anchor tags
    content = re.sub(r'<a id=[\'"][^\'"]*[\'"]></a>', '', content)
    
    # Remove image description tags
    content = re.sub(r'<::.*?::>', '', content, flags=re.DOTALL)
    
    # Convert HTML tables
    content = convert_html_table_to_markdown(content)
    
    return content

def convert_html_table_to_markdown(content):
    """Convert HTML tables to markdown format."""
    table_pattern = re.compile(r'<table[^>]*>(.*?)</table>', re.DOTALL | re.IGNORECASE)
    
    def replace_table(match):
        table_html = match.group(1)
        row_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
        rows = row_pattern.findall(table_html)
        
        if not rows:
            return ""
        
        markdown_rows = []
        max_cols = 0
        
        for row in rows:
            cell_pattern = re.compile(r'<t[dh]([^>]*)>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)
            cells_data = cell_pattern.findall(row)
            
            cleaned_cells = []
            for attrs, cell_content in cells_data:
                cell_text = re.sub(r'<[^>]+>', '', cell_content)
                cell_text = cell_text.strip()
                
                colspan_match = re.search(r'colspan=["\']?(\d+)["\']?', attrs, re.IGNORECASE)
                colspan = int(colspan_match.group(1)) if colspan_match else 1
                
                for _ in range(colspan):
                    cleaned_cells.append(cell_text)
            
            if cleaned_cells:
                max_cols = max(max_cols, len(cleaned_cells))
                markdown_row = "| " + " | ".join(cleaned_cells) + " |"
                markdown_rows.append(markdown_row)
        
        if len(markdown_rows) > 0:
            if len(markdown_rows) > 1:
                separator = "|" + "---|" * max_cols
                markdown_rows.insert(1, separator)
            else:
                separator = "|" + "---|" * max_cols
                markdown_rows.append(separator)
        
        return "\n\n" + "\n".join(markdown_rows) + "\n\n"
    
    return table_pattern.sub(replace_table, content)

def process_markdown_file(md_file_path):
    """Process file by translating paragraph by paragraph."""
    logger.info(f"Processing: {md_file_path}")
    
    try:
        # Read file
        with open(md_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Step 1: Clean HTML
        cleaned_content = clean_html_tags(content)
        
        # Step 2: Split into paragraphs
        paragraphs = cleaned_content.split('\n\n')
        
        # Step 3: Translate each paragraph
        translator = Translator()
        translated_paragraphs = []
        
        for i, para in enumerate(paragraphs):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(paragraphs)} paragraphs")
            
            if para.strip():
                # Check if paragraph contains table rows (multiple lines starting with |)
                lines = para.split('\n')
                if len(lines) > 1 and all(line.strip().startswith('|') and line.strip().endswith('|') for line in lines if line.strip()):
                    # It's a table - translate each row
                    translated_rows = []
                    for line in lines:
                        if line.strip():
                            if '---|' in line:
                                # It's a separator, keep as is
                                translated_rows.append(line)
                            else:
                                # Translate table cells
                                cells = [c.strip() for c in line.split('|')[1:-1]]
                                translated_cells = [translate_line(cell, translator) for cell in cells]
                                translated_row = "| " + " | ".join(translated_cells) + " |"
                                translated_rows.append(translated_row)
                        else:
                            translated_rows.append(line)
                    translated_paragraphs.append('\n'.join(translated_rows))
                # Check if it's a heading - translate specially
                elif re.match(r'^#{1,6}\s', para):
                    heading_match = re.match(r'^(#{1,6})\s+(.*)', para)
                    if heading_match:
                        level = heading_match.group(1)
                        text = heading_match.group(2)
                        translated_text = translate_line(text, translator)
                        translated_paragraphs.append(f"{level} {translated_text}")
                    else:
                        translated_paragraphs.append(para)
                else:
                    # Regular paragraph
                    translated_para = translate_line(para, translator)
                    translated_paragraphs.append(translated_para)
            else:
                translated_paragraphs.append(para)
        
        # Step 4: Join and clean up
        translated_content = '\n\n'.join(translated_paragraphs)
        translated_content = re.sub(r'\n\n\n+', '\n\n', translated_content)
        
        # Step 5: Save
        output_file = md_file_path.parent / "dpt2_result_translated.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(translated_content)
        
        logger.info(f"✓ Saved: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_file = Path("/home/aic_u1/aic_u1/pop_scraping/dpt2_processing/processed_data/Andra Pradesh/POP- Betelvine/dpt2_result.md")
    process_markdown_file(test_file)