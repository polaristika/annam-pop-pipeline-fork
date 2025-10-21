# Future Phases: Advanced PDF Processing

**Status:** 📋 Planned (350 PDFs remaining)  
**Completion:** 38.1% done (215/565), 61.9% to go  
**Last Updated:** October 21, 2025

---

## Table of Contents
1. [Overview](#overview)
2. [Phase 3: Scanned English PDFs](#phase-3-scanned-english-pdfs)
3. [Phase 4: Scanned Indic PDFs](#phase-4-scanned-indic-pdfs)
4. [Phase 5: Error Recovery](#phase-5-error-recovery)
5. [Phase 6: Garbled Text Processing](#phase-6-garbled-text-processing)
6. [Advanced Features](#advanced-features)
7. [Technical Approach](#technical-approach)
8. [Implementation Roadmap](#implementation-roadmap)

---

## Overview

### Current Status

| Phase | Type | Count | Status |
|-------|------|-------|--------|
| Phase 1 | Digital English | 152 | ✅ Complete |
| Phase 2 | Digital Indic | 63 | ✅ Complete |
| **Phase 3** | **Scanned English** | **42** | 📋 Planned |
| **Phase 4** | **Scanned Indic** | **5** | 📋 Planned |
| **Phase 5** | **Error Recovery** | **20** | 📋 Planned |
| **Phase 6** | **Garbled Files** | **283** | 📋 Planned |
| **Total** | | **565** | **38.1% done** |

### Remaining Challenges

The remaining 350 PDFs (61.9%) present more complex challenges:

1. **Scanned Documents** (47 PDFs)
   - Poor OCR quality
   - Image preprocessing needed
   - Lower confidence scores

2. **Mixed Content** (283 PDFs)
   - Garbled Unicode text
   - Mixed languages
   - Uncertain classification

3. **Errors & Edge Cases** (20 PDFs)
   - Corrupted files
   - Unusual formats
   - Very low quality

---

## Phase 3: Scanned English PDFs

### Overview

**Count:** 42 PDFs (7.4% of total)  
**Challenge:** Image-based PDFs requiring OCR  
**Estimated Time:** 5-10 hours processing

### Selection Criteria

```python
phase3_criteria = {
    'class': 'scanned_en',        # Classified as scanned
    'lang_guess': 'en',            # English language
    'digital_guess': False,        # Not born-digital
    'lang_conf': >= 0.5,          # Confident English
}
```

### Classification Logic

**How we identify scanned PDFs:**

```python
def classify_pdf_simple(pdf_path):
    """Basic classification based on extractable text."""
    
    # Extract text from first 5 pages
    text = extract_text(pdf_path, max_pages=5, max_chars=6000)
    
    # Check text length
    if len(text.strip()) < 200:
        # Very little text → likely scanned
        return "scanned_en" or "scanned_indic"
    else:
        # Good text extraction → digital
        return "digital_en" or "digital_indic"
```

### Processing Pipeline

```
┌─────────────────┐
│  Scanned PDF    │
│   (English)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Image          │ ◄── Extract each page as image
│  Extraction     │     (PDF → PNG at 300 DPI)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Preprocessing  │ ◄── Enhance image quality
│  (OpenCV)       │     - Deskew
└────────┬────────┘     - Denoise
         │              - Binarize
         ▼
┌─────────────────┐
│  EasyOCR        │ ◄── OCR with English model
│  (English)      │     High accuracy mode
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Structure      │ ◄── Detect headings, paragraphs
│  Detection      │     Tables, images
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  JSON + MD      │ ◄── Generate outputs
│  Generation     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Artifacts     │
└─────────────────┘
```

### Implementation Approach

#### Image Preprocessing

```python
import cv2
import numpy as np

def preprocess_image(image_path):
    """Enhance scanned image for better OCR."""
    
    # Load image
    img = cv2.imread(str(image_path))
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Deskew (correct rotation)
    angle = detect_skew(gray)
    if abs(angle) > 0.5:
        rotated = rotate_image(gray, angle)
    else:
        rotated = gray
    
    # Denoise
    denoised = cv2.fastNlMeansDenoising(rotated)
    
    # Adaptive threshold (binarize)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    
    # Enhance contrast
    enhanced = cv2.equalizeHist(binary)
    
    return enhanced
```

#### OCR with Error Handling

```python
def ocr_scanned_pdf(pdf_path, output_dir):
    """OCR entire scanned PDF."""
    
    import easyocr
    reader = easyocr.Reader(['en'], gpu=True)
    
    results = []
    
    # Convert PDF to images
    images = pdf_to_images(pdf_path, dpi=300)
    
    for page_num, image_path in enumerate(images, 1):
        # Preprocess
        enhanced = preprocess_image(image_path)
        
        # OCR
        try:
            ocr_result = reader.readtext(enhanced)
            
            # Extract text with confidence
            page_text = []
            for (bbox, text, conf) in ocr_result:
                if conf >= 0.5:  # Confidence threshold
                    page_text.append(text)
            
            results.append({
                'page': page_num,
                'text': '\n'.join(page_text),
                'confidence': np.mean([r[2] for r in ocr_result])
            })
            
        except Exception as e:
            log_error(f"OCR failed for page {page_num}: {e}")
            results.append({'page': page_num, 'error': str(e)})
    
    return results
```

#### Structure Detection

```python
def detect_structure(ocr_results):
    """Detect document structure from OCR text."""
    
    structured_blocks = []
    
    for page in ocr_results:
        text = page['text']
        lines = text.split('\n')
        
        for line in lines:
            # Detect headings (all caps, short, etc.)
            if line.isupper() and len(line) < 100:
                block = {
                    'type': 'heading',
                    'text': line.title(),
                    'confidence': page['confidence']
                }
            
            # Detect tables (multiple columns, numbers)
            elif detect_table_pattern(line):
                block = {
                    'type': 'table_row',
                    'text': line
                }
            
            # Regular paragraph
            else:
                block = {
                    'type': 'paragraph',
                    'text': line
                }
            
            structured_blocks.append(block)
    
    return structured_blocks
```

### Expected Challenges

1. **Low Image Quality**
   - **Solution:** Aggressive preprocessing, multiple OCR passes
   
2. **Poor Scan Alignment**
   - **Solution:** Deskew algorithms, perspective correction
   
3. **Mixed Fonts/Sizes**
   - **Solution:** Multi-scale OCR, adaptive thresholding
   
4. **Tables**
   - **Solution:** Table detection models, structured extraction

### Estimated Results

| Metric | Expected Value |
|--------|---------------|
| Success Rate | 85-90% |
| OCR Accuracy | 92-95% |
| Processing Time | 8-10 min per PDF |
| Manual Review Needed | 10-15% of PDFs |

---

## Phase 4: Scanned Indic PDFs

### Overview

**Count:** 5 PDFs (0.9% of total)  
**Challenge:** Scanned images + Indic scripts + translation  
**Estimated Time:** 2-3 hours processing

### Additional Challenges

Phase 4 combines challenges from Phase 2 (Indic) + Phase 3 (scanned):

1. **Multi-script OCR**
   - Devanagari, Tamil, Telugu scripts
   - Lower accuracy than English OCR
   
2. **Script-specific Preprocessing**
   - Different character shapes
   - Complex conjuncts (e.g., Hindi ligatures)
   
3. **Translation After OCR**
   - OCR errors compound in translation
   - Context loss

### Processing Approach

```python
# State-aware multi-script OCR
STATE_OCR_CONFIG = {
    'Maharashtra': {
        'scripts': ['mr', 'hi', 'en'],
        'preprocessing': 'aggressive',
        'confidence_threshold': 0.4  # Lower for Indic
    },
    'Tamil Nadu': {
        'scripts': ['ta', 'en'],
        'preprocessing': 'aggressive',
        'confidence_threshold': 0.4
    }
}

def process_scanned_indic_pdf(pdf_path, state, output_dir):
    """Process scanned Indic PDF."""
    
    config = STATE_OCR_CONFIG[state]
    
    # Multi-script OCR
    reader = easyocr.Reader(config['scripts'], gpu=True)
    
    # Enhanced preprocessing for Indic scripts
    images = preprocess_indic_scans(pdf_path)
    
    # OCR all pages
    ocr_results = []
    for img in images:
        result = reader.readtext(img)
        ocr_results.append(result)
    
    # Structure detection
    structured = detect_structure(ocr_results)
    
    # Translation
    translated = translate_document(structured, target='en')
    
    # Generate outputs
    generate_bilingual_outputs(translated, output_dir)
    
    return {'status': 'success'}
```

---

## Phase 5: Error Recovery

### Overview

**Count:** 20 PDFs (3.5% of total)  
**Challenge:** Corrupted, unusual, or problematic files  
**Approach:** Manual investigation + custom solutions

### Error Categories

From `data/metadata/classification_error.csv`:

| Error Type | Count | Approach |
|------------|-------|----------|
| Corrupted PDF | 8 | Try repair tools (pdftk, gs) |
| Unusual Format | 5 | Convert to standard PDF |
| Very Low Quality | 4 | Extreme preprocessing |
| Encrypted | 2 | Request unlocked version |
| Unknown | 1 | Manual analysis |

### Recovery Strategies

#### 1. PDF Repair
```bash
# Try ghostscript repair
gs -dNOPAUSE -dBATCH -sDEVICE=pdfwrite \
   -sOutputFile=repaired.pdf corrupted.pdf

# Try pdftk
pdftk corrupted.pdf output repaired.pdf
```

#### 2. Format Conversion
```python
# Convert unusual formats
from pdf2image import convert_from_path

def force_convert_pdf(pdf_path, output_path):
    """Convert to images then back to PDF."""
    
    # PDF → Images
    images = convert_from_path(pdf_path, dpi=300)
    
    # Images → New PDF
    images[0].save(output_path, save_all=True,
                   append_images=images[1:])
    
    return output_path
```

#### 3. Manual Processing
For truly problematic files:
1. Open in Adobe Acrobat
2. Print to PDF (creates clean version)
3. Process with Phase 3/4 pipeline

---

## Phase 6: Garbled Text Processing

### Overview

**Count:** 283 PDFs (50.1% of total)  
**Status:** ✅ **Partially Implemented** (pipeline exists)  
**Challenge:** Unicode corruption from encoding issues

### Problem Description

**Garbled Text Example:**
- **Original:** "मराठी शेती मार्गदर्शक"
- **Garbled:** "àƒÂ®àƒÂ°àƒÂ¾àƒÂ àƒÂ¶àƒÂ¿àƒÂ¤àƒÂ€"

**Cause:**
- Font encoding issues in PDF
- Incorrect character mapping
- Copy-paste corruption

### Solution: Phase 6 V2 Pipeline

**Already Implemented!** See `code/src/pipeline/phase6_improved_v2_json.py`

```python
class ImprovedPhase6PipelineV2:
    """Process PDFs with garbled Unicode text."""
    
    def process_pdf(self, pdf_path, state, output_dir):
        """
        1. Docling extract (preserves structure, text is garbled)
        2. Convert to JSON (structure preserved)
        3. Run state-aware OCR (clean text)
        4. Sequential text matching (replace garbled with OCR)
        5. Translation (if Indic)
        6. Generate outputs
        """
        
        # Steps 1-2: Structure with garbled text
        doc_garbled_json = self.extract_and_convert(pdf_path)
        
        # Step 3: Clean OCR
        ocr_results = self.run_state_aware_ocr(pdf_path, state)
        
        # Step 4: Replace garbled
        doc_clean = self.sequential_text_match(
            doc_garbled_json, ocr_results
        )
        
        # Step 5: Translate if needed
        if detect_language(doc_clean) != 'en':
            doc_translated = self.translate(doc_clean)
        else:
            doc_translated = doc_clean
        
        # Step 6: Generate outputs
        self.generate_outputs(doc_translated, output_dir)
        
        return {'status': 'success'}
```

### Next Steps for Phase 6

1. **Test on all 283 PDFs**
   ```bash
   python pop_cli.py batch --phase 6 --all
   ```

2. **Validate Outputs**
   - Check text replacement accuracy
   - Verify structure preservation
   - Review translation quality

3. **Optimize Performance**
   - Parallel processing
   - GPU acceleration
   - Batch OCR

---

## Advanced Features

### Future Enhancements

#### 1. Vision-Language Models (VLMs)
```python
from transformers import Blip2Processor, Blip2ForConditionalGeneration

def describe_agricultural_image(image_path):
    """Use VLM to describe agricultural images."""
    
    processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
    model = Blip2ForConditionalGeneration.from_pretrained("Salesforce/blip2-opt-2.7b")
    
    image = Image.open(image_path)
    inputs = processor(image, return_tensors="pt")
    
    generated_ids = model.generate(**inputs, max_length=100)
    caption = processor.decode(generated_ids[0], skip_special_tokens=True)
    
    return caption
```

#### 2. Knowledge Graph Construction
```python
# Extract entities and relationships
entities = extract_entities(document)
# {
#   'crops': ['Rice', 'Wheat', 'Cotton'],
#   'practices': ['Irrigation', 'Fertilization'],
#   'states': ['Maharashtra', 'Bihar']
# }

relationships = extract_relationships(document)
# [
#   ('Rice', 'grown_in', 'Maharashtra'),
#   ('Irrigation', 'required_for', 'Rice'),
# ]

# Build knowledge graph
build_knowledge_graph(entities, relationships)
```

#### 3. Multi-Modal Search
```bash
# Search by text
search("rice cultivation practices")

# Search by image
search_by_image("examples/rice_plant.jpg")

# Combined search
search("rice varieties", image="examples/rice_field.jpg")
```

---

## Technical Approach

### Recommended Tools

#### Image Processing
- **OpenCV** - Image preprocessing
- **Pillow** - Image manipulation
- **pdf2image** - PDF to image conversion

#### OCR
- **EasyOCR** - Multi-language OCR (current)
- **PaddleOCR** - Alternative, good for Chinese/Indic
- **Tesseract** - Fallback option

#### Translation
- **Google Translate** - Current solution
- **IndicTrans2** - Specialized for Indic languages (future)
- **M2M100** - Multi-lingual translation

#### Document Understanding
- **LayoutLM** - Document layout understanding
- **Donut** - Document understanding transformer
- **BLIP-2** - Vision-language model

### Pipeline Architecture

```python
class UnifiedPipeline:
    """Unified pipeline for all phases."""
    
    def __init__(self):
        self.classifier = PDFClassifier()
        self.ocr = OCREngine()
        self.translator = TranslationEngine()
        self.structurer = StructureEngine()
    
    def process_pdf(self, pdf_path):
        """Automatically route to appropriate phase."""
        
        # Classify
        classification = self.classifier.classify(pdf_path)
        
        # Route to appropriate handler
        if classification['route'] == 'digital_en':
            return self.process_phase1(pdf_path)
        elif classification['route'] == 'digital_indic':
            return self.process_phase2(pdf_path)
        elif classification['route'] == 'scanned_en':
            return self.process_phase3(pdf_path)
        elif classification['route'] == 'scanned_indic':
            return self.process_phase4(pdf_path)
        elif classification['garbled']:
            return self.process_phase6(pdf_path)
        else:
            return self.process_phase5(pdf_path)  # Error recovery
```

---

## Implementation Roadmap

### Phase 3: Scanned English (2-3 weeks)

**Week 1: Setup & Testing**
- [ ] Implement image preprocessing
- [ ] Test OCR accuracy on samples
- [ ] Develop structure detection

**Week 2: Full Implementation**
- [ ] Process all 42 PDFs
- [ ] Manual review and corrections
- [ ] Documentation

**Week 3: Optimization**
- [ ] Parallel processing
- [ ] Quality improvements
- [ ] CI/CD integration

### Phase 4: Scanned Indic (1-2 weeks)

**Week 1: Implementation**
- [ ] Multi-script OCR setup
- [ ] Process all 5 PDFs
- [ ] Quality review

**Week 2: Refinement**
- [ ] Translation validation
- [ ] Format standardization

### Phase 5: Error Recovery (1 week)

**Week 1: Case-by-case**
- [ ] Analyze each error
- [ ] Apply specific solutions
- [ ] Document patterns

### Phase 6: Garbled Processing (3-4 weeks)

**Week 1-2: Batch Processing**
- [ ] Run Phase 6 pipeline on all 283 PDFs
- [ ] Monitor progress
- [ ] Handle failures

**Week 3: Quality Assurance**
- [ ] Sample validation (10%)
- [ ] Accuracy measurements
- [ ] Error analysis

**Week 4: Documentation & Deployment**
- [ ] Update documentation
- [ ] Performance benchmarks
- [ ] Production deployment

### Total Timeline: 8-10 weeks

---

## Success Metrics

### Target Goals

| Phase | Target Success Rate | Target Accuracy |
|-------|-------------------|-----------------|
| Phase 3 | 85% | 92% OCR accuracy |
| Phase 4 | 80% | 88% OCR + translation |
| Phase 5 | 70% | Manual recovery |
| Phase 6 | 90% | 94% text replacement |

### Overall Project Goals

- **Process all 565 PDFs:** 100% completion
- **Overall success rate:** >85%
- **Structured outputs:** JSON + Markdown for all
- **Translation coverage:** All Indic content translated
- **Documentation:** Complete for all phases

---

## Conclusion

**Current Status:** 215/565 PDFs (38.1%) complete  
**Remaining:** 350 PDFs (61.9%) across 4 phases  
**Estimated Time:** 8-10 weeks of focused work  
**Technical Feasibility:** ✅ High (tools and pipelines ready)

**Next Steps:**
1. Prioritize Phase 3 (Scanned English) - most straightforward
2. Test Phase 6 pipeline on sample of garbled PDFs
3. Develop error recovery strategies for Phase 5
4. Plan Phase 4 with Indic language experts

**For detailed CLI usage, see:** `06_CLI_USER_GUIDE.md`
