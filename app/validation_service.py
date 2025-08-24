# validation_service.py
import os
import PyPDF2
import fitz  # PyMuPDF
import docx
import pytesseract
from PIL import Image
import spacy
import re
import requests
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime
from flask import current_app
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
    send_file,
    json
)


DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
API_KEY = "sk-c32b5df704424ae5a520b73c53f9af22"  # Replace with your actual key

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}




def extract_text_from_pdf(file_path):
    print(f"Extracting text from PDF: {file_path}")
    text = ""
    try:
        with open(file_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_number, page in enumerate(pdf_reader.pages):
                print(f"Extracting page {page_number + 1}")
                page_text = page.extract_text()
                if page_text:
                    text += page_text
    except Exception as e:
        print(f"Error reading PDF: {str(e)}")
    return text


def extract_text_from_docx(file_path):
    print(f"Extracting text from DOCX: {file_path}")
    text = ""
    try:
        doc = docx.Document(file_path)
        for i, paragraph in enumerate(doc.paragraphs):
            print(f"Reading paragraph {i + 1}")
            text += paragraph.text + "\n"
    except Exception as e:
        print(f"Error reading DOCX: {str(e)}")
    return text


def extract_text_from_image(file_path):
    """
    Extract text from image files (PNG, JPG) using OCR
    """
    print(f"Extracting text from image: {file_path}")
    try:
        # Open the image file
        image = Image.open(file_path)

        # Perform OCR
        text = pytesseract.image_to_string(image)
        print("OCR completed successfully")

        return text
    except Exception as e:
        print(f"Error in OCR: {str(e)}")
        return ""


def extract_text_from_file(file_path):
    """
    Extract text from various file types
    """
    print(f"Determining file type for: {file_path}")
    if file_path.lower().endswith(".pdf"):
        return extract_text_from_pdf(file_path)
    elif file_path.lower().endswith(".docx"):
        return extract_text_from_docx(file_path)
    elif file_path.lower().endswith((".png", ".jpg", ".jpeg")):
        return extract_text_from_image(file_path)
    else:
        print("Unsupported file type")
        return ""


def get_semantic_similarity(text1, text2):
    """
    Get semantic similarity between two texts using TF-IDF and cosine similarity
    Returns a similarity score between 0 and 1
    """
    try:
        # Create TF-IDF vectorizer
        vectorizer = TfidfVectorizer()

        # Fit and transform the texts
        tfidf_matrix = vectorizer.fit_transform([text1, text2])

        # Calculate cosine similarity
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

        return similarity
    except Exception as e:
        print(f"Error in semantic similarity: {str(e)}")
        return 0.0


def get_document_type(text):
    """
    Identify the type of document based on its content
    Returns a dictionary with document type and confidence score
    """
    # Common document type keywords and patterns with weights
    document_types = {
        "invoice": {
            "positive": {
                "invoice": 5,
                "bill": 3,
                "payment": 2,
                "amount due": 3,
                "total amount": 2,
                "invoice number": 3,
                "invoice date": 3,
                "due date": 2,
                "tax": 2,
                "subtotal": 2,
                "balance due": 2,
                "payment terms": 2,
                "invoice to": 3,
                "bill to": 3,
                "customer": 1,
                "client": 1,
                "items": 1,
                "quantity": 1,
                "unit price": 2,
                "total": 2,
                "vat": 1,
                "gst": 1,
                "tax amount": 2,
                "net amount": 2,
                "grand total": 2,
            },
            "negative": [
                "bill of lading",
                "shipping",
                "freight",
                "cargo",
                "vessel",
                "port",
                "consignee",
                "shipper",
                "carrier",
                "voyage",
                "container",
                "seal",
                "manifest",
            ],
        },
        "bill of lading": {
            "positive": {
                "bill of lading": 5,
                "shipping": 3,
                "freight": 3,
                "cargo": 3,
                "vessel": 3,
                "port": 3,
                "consignee": 3,
                "shipper": 3,
                "carrier": 3,
                "voyage": 3,
                "container": 3,
                "seal": 3,
                "manifest": 3,
                "loading": 2,
                "discharge": 2,
                "destination": 2,
                "origin": 2,
                "weight": 2,
                "measurement": 2,
                "packages": 2,
                "description": 2,
            },
            "negative": [
                "invoice",
                "payment",
                "amount due",
                "tax",
                "subtotal",
                "balance due",
                "payment terms",
                "unit price",
                "vat",
                "gst",
            ],
        },
        "receipt": {
            "positive": {
                "receipt": 5,
                "payment received": 3,
                "paid": 3,
                "payment confirmation": 3,
                "transaction": 2,
                "payment date": 2,
                "payment method": 2,
                "reference number": 2,
                "amount paid": 2,
                "received by": 2,
                "cash": 1,
                "credit card": 1,
                "debit card": 1,
                "bank transfer": 1,
            },
            "negative": [
                "bill of lading",
                "shipping",
                "freight",
                "cargo",
                "vessel",
                "port",
            ],
        },
    }

    text = text.lower()
    max_score = 0
    detected_type = None

    for doc_type, keywords in document_types.items():
        score = 0
        # Check positive keywords
        for keyword, weight in keywords["positive"].items():
            if keyword in text:
                score += weight

        # Check negative keywords
        for keyword in keywords["negative"]:
            if keyword in text:
                score -= 1  # Reduced penalty for negative keywords

        if score > max_score:
            max_score = score
            detected_type = doc_type

    # Calculate confidence score
    total_possible_score = (
        sum(document_types[detected_type]["positive"].values()) if detected_type else 0
    )
    confidence = (
        max_score / total_possible_score
        if detected_type and total_possible_score > 0
        else 0
    )

    return {"type": detected_type, "confidence": confidence}


def extract_content_from_text(text, field_name, section):
    """
    Extract specific content from text using advanced NLP and structured data extraction
    """
    print(f"Extracting '{field_name}' from '{section}' section")
    
    # Load English language model
    try:
        nlp = spacy.load("en_core_web_sm")
        print("Successfully loaded spaCy model")
    except:
        # If model not found, download it
        import subprocess
        print("spaCy model not found, downloading...")
        subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
        nlp = spacy.load("en_core_web_sm")
        print("spaCy model downloaded and loaded")

    # Preprocess text
    text = text.replace("\n", " ").replace("\r", " ")
    print(f"Preprocessed text length: {len(text)} characters")
    doc = nlp(text)
    print(f"Created spaCy document with {len(doc)} tokens")

    # Define advanced patterns for different sections
    patterns = {
        "header": {
            "invoice": [
                r"(?i)invoice\s*(?:number|no|#)?[:#]?\s*(\w+)",
                r"(?i)inv\.?\s*(?:number|no|#)?[:#]?\s*(\w+)",
                r"(?i)invoice\s*(?:number|no|#)?[:#]?\s*(\d+)",
                r"(?i)invoice\s*(?:number|no|#)?[:#]?\s*([A-Z0-9-]+)",
            ],
            "date": [
                r"(?i)(?:date|dated)[:#]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
                r"(?i)(?:date|dated)[:#]?\s*(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})",
                r"(?i)(?:date|dated)[:#]?\s*(\d{1,2}\s+\d{1,2}\s+\d{2,4})",
                r"(?i)(?:date|dated)[:#]?\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})",
            ],
            "from": [
                r"(?i)from[:#]?\s*([^\n]+)",
                r"(?i)sender[:#]?\s*([^\n]+)",
                r"(?i)issued by[:#]?\s*([^\n]+)",
                r"(?i)company[:#]?\s*([^\n]+)",
            ],
            "to": [
                r"(?i)(?:to|bill to)[:#]?\s*([^\n]+)",
                r"(?i)(?:recipient|client)[:#]?\s*([^\n]+)",
                r"(?i)(?:customer|buyer)[:#]?\s*([^\n]+)",
                r"(?i)(?:sold to|shipped to)[:#]?\s*([^\n]+)",
            ],
            "company": [
                r"(?i)company[:#]?\s*([^\n]+)",
                r"(?i)organization[:#]?\s*([^\n]+)",
                r"(?i)business[:#]?\s*([^\n]+)",
                r"(?i)vendor[:#]?\s*([^\n]+)",
            ],
        },
        "body": {
            "description": [
                r"(?i)description[:#]?\s*([^\n]+)",
                r"(?i)item[:#]?\s*([^\n]+)",
                r"(?i)product[:#]?\s*([^\n]+)",
                r"(?i)service[:#]?\s*([^\n]+)",
                r"(?i)goods[:#]?\s*([^\n]+)",
            ],
            "quantity": [
                r"(?i)quantity[:#]?\s*(\d+)",
                r"(?i)qty[:#]?\s*(\d+)",
                r"(?i)amount[:#]?\s*(\d+)",
                r"(?i)units[:#]?\s*(\d+)",
                r"(?i)number of[:#]?\s*(\d+)",
            ],
            "price": [
                r"(?i)(?:price|rate)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:unit price|unit cost)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:cost|amount)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:price per unit)[:#]?\s*(\d+(?:\.\d{2})?)",
            ],
            "amount": [
                r"(?i)amount[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)total[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)sum[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:line total|item total)[:#]?\s*(\d+(?:\.\d{2})?)",
            ],
            "tax": [
                r"(?i)(?:tax|vat|gst)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:tax rate|vat rate)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:tax amount|vat amount)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:sales tax|value added tax)[:#]?\s*(\d+(?:\.\d{2})?)",
            ],
        },
        "footer": {
            "total": [
                r"(?i)total[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)grand total[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)final amount[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:subtotal|net amount)[:#]?\s*(\d+(?:\.\d{2})?)",
            ],
            "tax": [
                r"(?i)(?:tax|vat|gst)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:total tax|total vat)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:tax amount|vat amount)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:total tax amount|total vat amount)[:#]?\s*(\d+(?:\.\d{2})?)",
            ],
            "grand_total": [
                r"(?i)(?:grand total|final amount)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:total amount|final total)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:amount due|balance due)[:#]?\s*(\d+(?:\.\d{2})?)",
                r"(?i)(?:total payable|amount payable)[:#]?\s*(\d+(?:\.\d{2})?)",
            ],
            "payment_terms": [
                r"(?i)payment terms[:#]?\s*([^\n]+)",
                r"(?i)terms[:#]?\s*([^\n]+)",
                r"(?i)payment conditions[:#]?\s*([^\n]+)",
                r"(?i)(?:payment method|payment mode)[:#]?\s*([^\n]+)",
            ],
            "due_date": [
                r"(?i)due date[:#]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
                r"(?i)payment due[:#]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
                r"(?i)due by[:#]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
                r"(?i)payment date[:#]?\s*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            ],
        },
    }
    print(f"Loaded {len(patterns)} sections with patterns")

    def clean_value(value):
        """Clean and normalize extracted values"""
        if not value:
            return None
        value = value.strip()
        # Remove extra spaces and normalize
        value = " ".join(value.split())
        return value

    def extract_structured_data(text, field_name, section):
        """Extract structured data using NLP"""
        print(f"Extracting structured data for {field_name} in {section}")
        results = []

        # Process the text with spaCy
        doc = nlp(text)

        # Extract entities
        for ent in doc.ents:
            if ent.label_ in ["MONEY", "PERCENT", "DATE", "ORG", "PERSON"]:
                results.append(ent.text)
                print(f"Found entity: {ent.text} (type: {ent.label_})")

        # Extract numbers and amounts
        if field_name.lower() in ["price", "amount", "total", "tax"]:
            money_pattern = r"\$\s*\d+(?:\.\d{2})?|\d+(?:\.\d{2})?\s*(?:USD|EUR|GBP)?"
            money_matches = re.findall(money_pattern, text)
            results.extend(money_matches)
            print(f"Found money values: {money_matches}")

        # Extract dates
        if field_name.lower() in ["date", "due_date"]:
            date_pattern = r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}"
            date_matches = re.findall(date_pattern, text)
            results.extend(date_matches)
            print(f"Found date values: {date_matches}")

        print(f"Structured data extraction results: {results}")
        return results

    def extract_with_patterns(text, field_name, section):
        """Extract content using regex patterns"""
        print(f"Extracting with regex patterns for {field_name} in {section}")
        values = []
        if section in patterns and field_name.lower() in patterns[section]:
            for pattern in patterns[section][field_name.lower()]:
                print(f"Trying pattern: {pattern}")
                matches = re.finditer(pattern, text)
                for match in matches:
                    value = clean_value(match.group(1))
                    print(f"Found match: {value}")
                    if value and value not in values:
                        values.append(value)
        print(f"Pattern extraction results: {values}")
        return values

    # For body section, we want to collect all matches
    if section == "body":
        print("Processing body section - collecting all matches")
        values = []

        # First try structured data extraction
        structured_values = extract_structured_data(text, field_name, section)
        values.extend(structured_values)
        print(f"After structured extraction, values: {values}")

        # Then try pattern matching
        pattern_values = extract_with_patterns(text, field_name, section)
        values.extend(pattern_values)
        print(f"After pattern matching, values: {values}")

        # Remove duplicates and clean values
        values = list(set(clean_value(v) for v in values if v))
        print(f"Final result for {field_name} in {section}: {values}")
        return values if values else None
    else:
        print(f"Processing {section} section - looking for first match")
        # For header and footer, we want the first match
        if section in patterns and field_name.lower() in patterns[section]:
            # Try structured data first
            structured_values = extract_structured_data(text, field_name, section)
            if structured_values:
                result = clean_value(structured_values[0])
                print(f"Found result from structured data: {result}")
                return result

            # Then try pattern matching
            for pattern in patterns[section][field_name.lower()]:
                match = re.search(pattern, text)
                if match:
                    result = clean_value(match.group(1))
                    print(f"Found result from pattern matching: {result}")
                    return result

    print(f"No results found for {field_name} in {section}")
    return None


def validate_document(submitted_text, sample_text, sample_document):
    print(f"Starting document validation process")
    print(f"Sample document: {sample_document.sample_file_path}")
    print(f"Submitted text length: {len(submitted_text)} characters")
    print(f"Sample text length: {len(sample_text)} characters")
    
    # Get dynamic thresholds from the sample document
    confidence_threshold = sample_document.confidence_level / 100  # Convert percentage to decimal
    content_similarity_threshold = sample_document.content_similarity  # Use as percentage
    
    print(f"Using dynamic thresholds:")
    print(f"  - Confidence threshold: {confidence_threshold:.1%}")
    print(f"  - Content similarity threshold: {content_similarity_threshold}%")

    # Identify document types
    print("Identifying document types...")
    submitted_doc_type = get_document_type(submitted_text)
    sample_doc_type = get_document_type(sample_text)
    
    print(f"Submitted document type: {submitted_doc_type['type']} with confidence {submitted_doc_type['confidence']:.2%}")
    print(f"Sample document type: {sample_doc_type['type']} with confidence {sample_doc_type['confidence']:.2%}")

    # Check if documents are of the same type and have sufficient confidence
    # Use dynamic confidence threshold
    if (
        submitted_doc_type["type"] != sample_doc_type["type"]
        or submitted_doc_type["confidence"] < confidence_threshold
        or sample_doc_type["confidence"] < confidence_threshold
    ):
        print(f"VALIDATION FAILED: Document type mismatch or confidence below threshold ({confidence_threshold:.1%})")
        return {
            "error": True,
            "message": f"Document type mismatch or insufficient confidence. Sample document is a {sample_doc_type['type']} (confidence: {sample_doc_type['confidence']:.2%}), but submitted document appears to be a {submitted_doc_type['type']} (confidence: {submitted_doc_type['confidence']:.2%}). Required confidence threshold: {confidence_threshold:.1%}",
            "document_similarity": 0,
            "thresholds": {
                "confidence_level": confidence_threshold * 100,
                "content_similarity": content_similarity_threshold
            }
        }

    # If documents are of the same type, proceed with field matching
    print("Documents are of the same type. Proceeding with field matching...")
    key_fields = json.loads(sample_document.key_fields)
    print(f"Found {len(key_fields)} key fields to validate")
    
    validation_results = {}
    extracted_content = {}
    match_count = 0

    for i, field in enumerate(key_fields):
        field_name = field["name"]
        field_section = field.get("section", "body")
        print(f"\nProcessing field {i+1}/{len(key_fields)}: '{field_name}' in section '{field_section}'")

        # Find the most similar field in the submitted text
        best_similarity = 0
        best_match = None

        # Split submitted text into words and create potential field names
        words = submitted_text.lower().split()
        print(f"Generating potential matches from {len(words)} words")
        
        potential_matches_checked = 0
        for i in range(len(words)):
            for j in range(i + 1, min(i + 5, len(words) + 1)):
                potential_field = " ".join(words[i:j])
                potential_matches_checked += 1
                
                if potential_matches_checked % 1000 == 0:
                    print(f"Checked {potential_matches_checked} potential matches...")
                
                similarity = get_semantic_similarity(
                    field_name.lower(), potential_field
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = potential_field
                    print(f"New best match: '{best_match}' with similarity {best_similarity:.2%}")

        print(f"Best match for '{field_name}': '{best_match}' with similarity {best_similarity:.2%}")
        
        # Consider it a match if similarity is above threshold
        # Still using 0.5 threshold for individual field matching as this is different from overall content similarity
        if best_similarity >= 0.5:  # 50% similarity threshold
            print(f"MATCH FOUND: Similarity above threshold (0.5)")
            validation_results[field_name] = {
                "matched": True,
                "similarity": best_similarity,
                "matched_with": best_match,
                "section": field_section,
            }
            # Extract the actual content
            print(f"Extracting content for '{field_name}' in section '{field_section}'")
            content = extract_content_from_text(
                submitted_text, field_name, field_section
            )
            if content:
                print(f"Extracted content: {content}")
                extracted_content[field_name] = {
                    "value": content,
                    "section": field_section,
                }
            else:
                print(f"No content extracted for '{field_name}'")
            match_count += 1
        else:
            print(f"NO MATCH: Similarity below threshold (0.5)")
            validation_results[field_name] = {
                "matched": False,
                "similarity": best_similarity,
                "matched_with": None,
                "section": field_section,
            }

    match_percentage = (match_count / len(key_fields)) * 100
    print(f"\nValidation complete: {match_count}/{len(key_fields)} fields matched ({match_percentage:.1f}%)")
    print(f"Content similarity threshold: {content_similarity_threshold}%")
    
    return {
        "error": False,
        "document_similarity": 1.0,
        "validation_results": validation_results,
        "extracted_content": extracted_content,
        "match_percentage": match_percentage,
        "thresholds": {
            "confidence_level": confidence_threshold * 100,
            "content_similarity": content_similarity_threshold
        }
    }


def extract_invoice_json(text):
    print(f"Starting invoice JSON extraction")
    print(f"Text length: {len(text)} characters")
    print(f"First 100 characters: {text[:100]}...")
    
    # Example: extract sender, recipient, invoice details, line items, totals
    invoice = {}

    # Extract sender (from)
    print("Extracting sender information...")
    from_block = re.search(r"From:(.*?)Invoice Number:", text, re.DOTALL)
    if from_block:
        invoice["from"] = from_block.group(1).strip()
        print(f"Found sender: {invoice['from']}")
    else:
        invoice["from"] = ""
        print("No sender information found")

    # Extract recipient (to)
    print("Extracting recipient information...")
    to_block = re.search(r"To:(.*?)Service Description:", text, re.DOTALL)
    if to_block:
        invoice["to"] = to_block.group(1).strip()
        print(f"Found recipient: {invoice['to']}")
    else:
        invoice["to"] = ""
        print("No recipient information found")

    # Extract invoice details
    print("Extracting invoice number...")
    invoice_number = re.search(r"Invoice Number[:\s]+([A-Za-z0-9-]+)", text)
    if invoice_number:
        invoice["invoice_number"] = invoice_number.group(1)
        print(f"Found invoice number: {invoice['invoice_number']}")
    else:
        invoice["invoice_number"] = ""
        print("No invoice number found")

    # Extract line items (services)
    print("Extracting line items (services)...")
    services = []
    service_matches = list(re.finditer(r"Service Description:(.*?)€", text, re.DOTALL))
    print(f"Found {len(service_matches)} potential service descriptions")
    
    for i, match in enumerate(service_matches):
        service = match.group(1).strip()
        print(f"Service {i+1}: {service}")
        services.append(service)
    
    invoice["services"] = services

    # Extract totals
    print("Extracting total amount...")
    total = re.search(r"Total[:\s]+([0-9\.,]+ €)", text)
    if total:
        invoice["total"] = total.group(1)
        print(f"Found total: {invoice['total']}")
    else:
        invoice["total"] = ""
        print("No total amount found")

    # Try alternative patterns if main patterns failed
    if not invoice["from"]:
        print("Trying alternative pattern for sender...")
        alt_from = re.search(r"(?:From|Sender|Company):(.*?)(?:To|Bill To|Invoice)", text, re.DOTALL)
        if alt_from:
            invoice["from"] = alt_from.group(1).strip()
            print(f"Found sender with alternative pattern: {invoice['from']}")
        else:
            print("Alternative pattern for sender also failed")
    
    if not invoice["to"]:
        print("Trying alternative pattern for recipient...")
        alt_to = re.search(r"(?:To|Bill To|Recipient):(.*?)(?:Service|Description|Date)", text, re.DOTALL)
        if alt_to:
            invoice["to"] = alt_to.group(1).strip()
            print(f"Found recipient with alternative pattern: {invoice['to']}")
        else:
            print("Alternative pattern for recipient also failed")
    
    if not invoice["invoice_number"]:
        print("Trying alternative pattern for invoice number...")
        alt_invoice = re.search(r"(?:Invoice|INV)[.\s#:]+([A-Za-z0-9-]+)", text, re.IGNORECASE)
        if alt_invoice:
            invoice["invoice_number"] = alt_invoice.group(1)
            print(f"Found invoice number with alternative pattern: {invoice['invoice_number']}")
        else:
            print("Alternative pattern for invoice number also failed")
    
    if not invoice["total"]:
        print("Trying alternative pattern for total amount...")
        alt_total = re.search(r"(?:Total Amount|Grand Total|Amount Due)[:\s]+([0-9\.,]+\s*[€$£])", text, re.IGNORECASE)
        if alt_total:
            invoice["total"] = alt_total.group(1)
            print(f"Found total with alternative pattern: {invoice['total']}")
        else:
            print("Alternative pattern for total amount also failed")

    # Print summary of extraction results
    print("\nExtraction Summary:")
    for key, value in invoice.items():
        if isinstance(value, list):
            print(f"- {key}: {len(value)} items extracted")
        else:
            print(f"- {key}: {'✓ Found' if value else '✗ Not found'}")

    return invoice



def calculate_cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors"""
    dot_product = np.dot(vec1, vec2)
    norm_a = np.linalg.norm(vec1)
    norm_b = np.linalg.norm(vec2)
    return dot_product / (norm_a * norm_b)

def validate_using_ai(submitted_text, sample_text, key_fields):
    """
    Validate document by comparing submitted text against sample text using AI embeddings.
    """
    print(f"Starting AI-powered document validation")
    
    # Initialize results
    validation_results = {}
    extracted_content = {}
    
    try:
        # API configuration (validate these values!)
        api_key = current_app.config.get("DEEPSEEK_API_KEY") 
        api_url = current_app.config.get("DEEPSEEK_API_URL")
        
        if not api_key:
            raise ValueError("DeepSeek API key not configured")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # --- Document-level embeddings ---
        def get_embedding(text):
            """Helper function to get embeddings."""
            data = {
                "input": text[:2000],  # Safer truncation
                "model": "deepseek-chat"  # Verify model name!
            }
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()  # Raises HTTPError for bad responses
            return response.json()["data"][0]["embedding"]  # Adjust if structure differs

        print("Getting document-level embeddings...")
        submitted_embedding = get_embedding(submitted_text)
        sample_embedding = get_embedding(sample_text)
        
        # Calculate similarity
        document_similarity = calculate_cosine_similarity(submitted_embedding, sample_embedding)
        print(f"Document-level similarity: {document_similarity:.4f}")

        # --- Field-level validation ---
        match_count = 0
        for field in key_fields:
            field_name = field["name"]
            print(f"Processing field: {field_name}")

            # Simulate field extraction (replace with actual logic)
            prompt = f"Extract the '{field_name}' field from: {submitted_text[:1000]}"
            field_embedding = get_embedding(prompt)
            field_similarity = calculate_cosine_similarity(field_embedding, submitted_embedding)
            
            is_match = field_similarity >= 0.5
            if is_match:
                match_count += 1

            validation_results[field_name] = {
                "matched": is_match,
                "similarity": field_similarity,
                "section": field.get("section", "body")
            }

        # Results
        match_percentage = (match_count / len(key_fields)) * 100 if key_fields else 0
        return {
            "error": False,
            "document_similarity": document_similarity,
            "validation_results": validation_results,
            "match_percentage": match_percentage
        }

    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}")
        return {
            "error": True,
            "message": f"API Error: {str(e)}",
            "validation_results": {}
        }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            "error": True,
            "message": f"Validation failed: {str(e)}",
            "validation_results": {}
        }


# NEW FUNCTION


def send_to_deepseek(text):
    prompt = f"""Extract structured information as key-value pairs from the following text. 
The response must be a valid Python dictionary. Only return the dictionary.

Text:
{text}
"""

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are an intelligent document parser."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    response = requests.post(DEEPSEEK_API_URL, headers=HEADERS, json=payload)
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]

    # Remove markdown code blocks like ```python ... ```
    cleaned_content = re.sub(r"```(?:python)?(.*?)```", r"\1", content, flags=re.DOTALL).strip()

    try:
        result_dict = eval(cleaned_content, {"__builtins__": {}})
    except Exception as e:
        print("Failed to evaluate content. Raw content from DeepSeek:\n", cleaned_content)
        raise ValueError("Failed to parse DeepSeek response into dictionary") from e

    return result_dict


