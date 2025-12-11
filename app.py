"""
PDFUtils - A Flet desktop app for PDF management
Provides functions to open, display, reorder, merge, and print PDF files.
"""

import flet as ft
import os
import logging
import json
import tempfile
import shutil
import platform
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Optional
from dateutil import parser as date_parser

# Try to import PyMuPDF (fitz), provide fallback error message
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Try to import spaCy for NER
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

# Configure logging
# Ensure logfiles directory exists
log_dir = "logfiles"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = os.path.join(log_dir, f"pdfutils_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Reduce Flet's logging verbosity
logging.getLogger('flet').setLevel(logging.WARNING)
logging.getLogger('flet_core').setLevel(logging.WARNING)
logging.getLogger('flet_desktop').setLevel(logging.WARNING)

# Persistent storage file
PERSISTENCE_FILE = "persistent.json"


class PersistentStorage:
    """Handle persistent storage of UI state and function usage"""
    
    def __init__(self):
        self.data = self.load()
    
    def load(self) -> dict:
        """Load persistent data from file"""
        try:
            if os.path.exists(PERSISTENCE_FILE):
                with open(PERSISTENCE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded persistent data from {PERSISTENCE_FILE}")
                return data
        except Exception as e:
            logger.warning(f"Could not load persistent data: {str(e)}")
        
        # Return default structure
        return {
            "ui_state": {
                "last_directory": "",
            },
            "function_usage": {}
        }
    
    def save(self):
        """Save persistent data to file"""
        try:
            with open(PERSISTENCE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved persistent data to {PERSISTENCE_FILE}")
        except Exception as e:
            logger.error(f"Could not save persistent data: {str(e)}")
    
    def set_ui_state(self, field: str, value: str):
        """Update UI state field"""
        self.data["ui_state"][field] = value
        self.save()
    
    def get_ui_state(self, field: str, default: str = "") -> str:
        """Get UI state field"""
        return self.data["ui_state"].get(field, default)
    
    def record_function_usage(self, function_name: str):
        """Record that a function was used"""
        if function_name not in self.data["function_usage"]:
            self.data["function_usage"][function_name] = {"count": 0}
        
        self.data["function_usage"][function_name]["last_used"] = datetime.now().isoformat()
        self.data["function_usage"][function_name]["count"] = self.data["function_usage"][function_name].get("count", 0) + 1
        self.save()
    
    def get_function_usage(self, function_name: str) -> dict:
        """Get usage stats for a function"""
        return self.data["function_usage"].get(function_name, {"last_used": None, "count": 0})


class PDFManager:
    """Main class for PDF management operations"""
    
    def __init__(self, log_callback=None):
        logger.info("Initializing PDFManager")
        self.log_callback = log_callback
        self.loaded_pdfs = []  # List of loaded PDF file paths
        self.pdf_pages = []  # List of (pdf_index, page_number, pdf_path) tuples for ordering
        self.current_preview_pdf = None  # Currently previewed PDF path
        self.current_preview_page = 0  # Current page number for preview
        self.temp_dir = tempfile.mkdtemp(prefix="pdfutils_")
        logger.debug(f"Temp directory created: {self.temp_dir}")
        
        if not PYMUPDF_AVAILABLE:
            self.log("WARNING: PyMuPDF not installed. PDF operations will be limited.", logging.WARNING)
    
    def log(self, message, level=logging.INFO):
        """Log a message and send to UI callback"""
        logger.log(level, message)
        if self.log_callback:
            self.log_callback(message)
    
    def cleanup(self):
        """Clean up temporary files"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temp directory: {str(e)}")
    
    def load_pdf_files(self, file_paths: list) -> Tuple[bool, str]:
        """
        Load multiple PDF files
        
        Args:
            file_paths: List of paths to PDF files
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not PYMUPDF_AVAILABLE:
            return False, "PyMuPDF library not available. Please install it with: pip install PyMuPDF"
        
        self.log(f"Loading {len(file_paths)} PDF file(s)...")
        
        loaded_count = 0
        failed_files = []
        
        for file_path in file_paths:
            try:
                # Validate it's a PDF
                doc = fitz.open(file_path)
                page_count = len(doc)
                doc.close()
                
                if file_path not in self.loaded_pdfs:
                    self.loaded_pdfs.append(file_path)
                    # Add all pages from this PDF to the page list
                    pdf_index = len(self.loaded_pdfs) - 1
                    for page_num in range(page_count):
                        self.pdf_pages.append((pdf_index, page_num, file_path))
                    loaded_count += 1
                    self.log(f"Loaded: {os.path.basename(file_path)} ({page_count} pages)")
                else:
                    self.log(f"Skipped (already loaded): {os.path.basename(file_path)}")
                    
            except Exception as e:
                failed_files.append((file_path, str(e)))
                self.log(f"Failed to load {os.path.basename(file_path)}: {str(e)}", logging.ERROR)
        
        if failed_files:
            return False, f"Loaded {loaded_count} file(s), {len(failed_files)} failed"
        
        return True, f"Successfully loaded {loaded_count} PDF file(s)"
    
    def clear_all_pdfs(self):
        """Clear all loaded PDFs"""
        self.loaded_pdfs = []
        self.pdf_pages = []
        self.current_preview_pdf = None
        self.current_preview_page = 0
        self.log("All PDFs cleared")
    
    def get_pdf_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF"""
        if not PYMUPDF_AVAILABLE:
            return 0
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception as e:
            self.log(f"Error getting page count: {str(e)}", logging.ERROR)
            return 0
    
    def render_pdf_page_to_image(self, pdf_path: str, page_num: int, zoom: float = 1.0) -> str:
        """
        Render a PDF page to an image file
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number (0-indexed)
            zoom: Zoom factor (1.0 = 100%)
            
        Returns:
            Path to the rendered image file
        """
        if not PYMUPDF_AVAILABLE:
            return ""
        
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num]
            
            # Render page to pixmap
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Save to temp file
            img_path = os.path.join(self.temp_dir, f"page_{hash(pdf_path)}_{page_num}.png")
            pix.save(img_path)
            
            doc.close()
            return img_path
            
        except Exception as e:
            self.log(f"Error rendering page: {str(e)}", logging.ERROR)
            return ""
    
    def reorder_pages(self, new_order: list):
        """
        Reorder the pages based on new order
        
        Args:
            new_order: List of (pdf_index, page_number, pdf_path) tuples in new order
        """
        self.pdf_pages = new_order
        self.log(f"Pages reordered: {len(new_order)} pages")
    
    def move_page(self, from_index: int, to_index: int):
        """
        Move a page from one position to another
        
        Args:
            from_index: Current index of the page
            to_index: New index for the page
        """
        if 0 <= from_index < len(self.pdf_pages) and 0 <= to_index < len(self.pdf_pages):
            page = self.pdf_pages.pop(from_index)
            self.pdf_pages.insert(to_index, page)
            self.log(f"Moved page from position {from_index + 1} to {to_index + 1}")
    
    def remove_page(self, page_index: int):
        """Remove a page from the list"""
        if 0 <= page_index < len(self.pdf_pages):
            removed = self.pdf_pages.pop(page_index)
            pdf_name = os.path.basename(removed[2])
            self.log(f"Removed page {removed[1] + 1} from {pdf_name}")
    
    def merge_pdfs(self, output_path: str) -> Tuple[bool, str]:
        """
        Merge all loaded PDFs according to current page order
        
        Args:
            output_path: Path for the output merged PDF
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not PYMUPDF_AVAILABLE:
            return False, "PyMuPDF library not available"
        
        if not self.pdf_pages:
            return False, "No pages to merge"
        
        self.log(f"Merging {len(self.pdf_pages)} pages into {output_path}...")
        
        try:
            # Create new PDF document
            output_doc = fitz.open()
            
            # Group pages by source PDF to minimize file opens
            pdf_docs = {}
            
            for pdf_index, page_num, pdf_path in self.pdf_pages:
                if pdf_path not in pdf_docs:
                    pdf_docs[pdf_path] = fitz.open(pdf_path)
            
            # Insert pages in order
            for pdf_index, page_num, pdf_path in self.pdf_pages:
                source_doc = pdf_docs[pdf_path]
                output_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)
            
            # Save the merged PDF
            output_doc.save(output_path)
            
            # Close all documents
            for doc in pdf_docs.values():
                doc.close()
            output_doc.close()
            
            self.log(f"Successfully merged {len(self.pdf_pages)} pages to {output_path}")
            return True, f"Successfully merged {len(self.pdf_pages)} pages to {os.path.basename(output_path)}"
            
        except Exception as e:
            self.log(f"Error merging PDFs: {str(e)}", logging.ERROR)
            return False, f"Error merging PDFs: {str(e)}"
    
    def print_pdf(self, pdf_path: str) -> Tuple[bool, str]:
        """
        Print a PDF file using the system's default print mechanism
        
        Args:
            pdf_path: Path to the PDF file to print
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not os.path.exists(pdf_path):
            return False, f"File not found: {pdf_path}"
        
        # Validate the file path is within allowed directories (temp dir or loaded PDFs)
        abs_path = os.path.abspath(pdf_path)
        is_valid_path = (
            abs_path.startswith(self.temp_dir) or
            abs_path in [os.path.abspath(p) for p in self.loaded_pdfs]
        )
        
        if not is_valid_path:
            self.log(f"Security: Attempted to print file outside allowed paths: {abs_path}", logging.WARNING)
            return False, "Cannot print file: path not in allowed directories"
        
        self.log(f"Printing: {os.path.basename(pdf_path)}...")
        
        try:
            system = platform.system()
            
            if system == "Windows":
                # Use Windows print command
                os.startfile(pdf_path, "print")
                return True, f"Sent to print: {os.path.basename(pdf_path)}"
                
            elif system == "Darwin":  # macOS
                # Open in Preview with print dialog
                # Using 'open' with Preview allows the user to see print dialog
                result = subprocess.run(["open", "-a", "Preview", pdf_path], capture_output=True, text=True)
                if result.returncode == 0:
                    return True, f"Opened in Preview for printing: {os.path.basename(pdf_path)}"
                else:
                    self.log(f"Preview open failed, trying lpr: {result.stderr}", logging.WARNING)
                    # Fallback to lpr if Preview fails
                    result = subprocess.run(["lpr", pdf_path], capture_output=True, text=True)
                    if result.returncode == 0:
                        return True, f"Sent to print: {os.path.basename(pdf_path)}"
                    else:
                        return False, f"Print failed: {result.stderr}"
                    
            else:  # Linux
                # Use lpr command on Linux
                result = subprocess.run(["lpr", pdf_path], capture_output=True, text=True)
                if result.returncode == 0:
                    return True, f"Sent to print: {os.path.basename(pdf_path)}"
                else:
                    return False, f"Print failed: {result.stderr}"
                    
        except Exception as e:
            self.log(f"Error printing PDF: {str(e)}", logging.ERROR)
            return False, f"Error printing PDF: {str(e)}"
    
    def export_page_to_png(self, pdf_path: str, page_num: int, output_path: str, dpi: int = 300) -> Tuple[bool, str]:
        """
        Export a PDF page to a PNG image file
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number (0-indexed)
            output_path: Path where the PNG should be saved
            dpi: Resolution in dots per inch (default: 300)
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not PYMUPDF_AVAILABLE:
            return False, "PyMuPDF is not available"
        
        if not os.path.exists(pdf_path):
            return False, f"PDF file not found: {pdf_path}"
        
        try:
            # Ensure output has .png extension
            if not output_path.lower().endswith('.png'):
                output_path += '.png'
            
            # Open PDF and get the page
            doc = fitz.open(pdf_path)
            
            if page_num < 0 or page_num >= len(doc):
                doc.close()
                return False, f"Invalid page number: {page_num + 1} (PDF has {len(doc)} pages)"
            
            page = doc[page_num]
            
            # Calculate zoom factor based on DPI
            # 72 is the default DPI for PDF
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat)
            
            # Save to PNG file
            pix.save(output_path)
            
            doc.close()
            
            pdf_name = os.path.basename(pdf_path)
            self.log(f"Exported page {page_num + 1} from {pdf_name} to {os.path.basename(output_path)}")
            return True, f"Page {page_num + 1} exported to: {os.path.basename(output_path)}"
            
        except Exception as e:
            self.log(f"Error exporting page to PNG: {str(e)}", logging.ERROR)
            return False, f"Error exporting page: {str(e)}"
    
    def get_loaded_pdf_info(self) -> list:
        """
        Get information about all loaded PDFs
        
        Returns:
            List of dicts with PDF info (path, name, page_count)
        """
        if not PYMUPDF_AVAILABLE:
            return []
        
        info_list = []
        for pdf_path in self.loaded_pdfs:
            try:
                doc = fitz.open(pdf_path)
                info_list.append({
                    "path": pdf_path,
                    "name": os.path.basename(pdf_path),
                    "page_count": len(doc)
                })
                doc.close()
            except Exception:
                info_list.append({
                    "path": pdf_path,
                    "name": os.path.basename(pdf_path),
                    "page_count": 0
                })
        return info_list
    
    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 3) -> str:
        """
        Extract text from the first few pages of a PDF
        
        Args:
            pdf_path: Path to the PDF file
            max_pages: Maximum number of pages to extract text from
            
        Returns:
            Extracted text as a string
        """
        if not PYMUPDF_AVAILABLE:
            return ""
        
        try:
            doc = fitz.open(pdf_path)
            text = ""
            pages_to_extract = min(max_pages, len(doc))
            
            for page_num in range(pages_to_extract):
                page = doc[page_num]
                text += page.get_text()
            
            doc.close()
            return text
        except Exception as e:
            self.log(f"Error extracting text: {str(e)}", logging.ERROR)
            return ""
    
    def analyze_pdf_content(self, pdf_path: str) -> Dict[str, any]:
        """
        Analyze PDF content to extract dates, names, and organizations
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing found dates, names, and organizations
        """
        text = self.extract_text_from_pdf(pdf_path, max_pages=3)
        
        if not text:
            return {"dates": [], "names": [], "organizations": []}
        
        result = {
            "dates": [],
            "names": [],
            "organizations": []
        }
        
        # Extract dates using regex patterns
        date_patterns = [
            r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b',  # MM/DD/YYYY or MM-DD-YYYY
            r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b',    # YYYY-MM-DD
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',  # Month DD, YYYY
            r'\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\b'  # DD Month YYYY
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Try to parse the date
                    parsed_date = date_parser.parse(match, fuzzy=True)
                    date_str = parsed_date.strftime("%Y-%m-%d")
                    if date_str not in result["dates"]:
                        result["dates"].append(date_str)
                except:
                    pass
        
        # Use spaCy for named entity recognition if available
        if SPACY_AVAILABLE:
            try:
                # Try to load the model, but don't fail if it's not available
                nlp = spacy.load("en_core_web_sm")
                doc = nlp(text[:10000])  # Limit to first 10k characters
                
                # Whitelist of allowed personal names for renaming
                allowed_names = ["Mark", "Christine", "Mark & Christine", "Mackenzie", "Morgan"]
                
                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        name = ent.text.strip()
                        # Only include if it matches one of the allowed names (case-insensitive)
                        if name and any(allowed.lower() in name.lower() for allowed in allowed_names):
                            # Find the matching allowed name and use that exact format
                            for allowed in allowed_names:
                                if allowed.lower() in name.lower():
                                    if allowed not in result["names"]:
                                        result["names"].append(allowed)
                                    break
                    elif ent.label_ in ["ORG", "PRODUCT", "FAC"]:
                        org = ent.text.strip()
                        # Filter out addresses (contains street indicators and numbers)
                        is_address = bool(re.search(r'\d+\s+(?:W\.|E\.|N\.|S\.|West|East|North|South)?\s*\w+\s+(?:St\.|Street|Ave\.|Avenue|Rd\.|Road|Blvd\.|Boulevard|Dr\.|Drive|Lane|Ln\.|Way)', org, re.IGNORECASE))
                        if org and len(org) > 2 and org not in result["organizations"] and not is_address:
                            result["organizations"].append(org)
            except Exception as e:
                self.log(f"Note: spaCy NER not available ({str(e)}). Using basic pattern matching.", logging.INFO)
        
        # Fallback: Use simple pattern matching for common service providers
        common_providers = [
            r'\b(?:Verizon|AT&T|T-Mobile|Sprint|Comcast|Xfinity|Cox|Spectrum)\b',
            r'\b(?:Amazon|Microsoft|Google|Apple|Facebook|Meta|Netflix)\b',
            r'\b(?:Bank of America|Wells Fargo|Chase|Citibank|Capital One|US Bank)\b',
            r'\b(?:Kaiser|Blue Cross|Blue Shield|Aetna|United Healthcare|Cigna|Humana)\b',
            r'\b(?:PG&E|Edison|Duke Energy|ConEd|National Grid)\b',
            r'\b(?:State Farm|Geico|Progressive|Allstate|Farmers)\b'
        ]
        
        for pattern in common_providers:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if match not in result["organizations"]:
                    result["organizations"].append(match)
        
        # Post-process to filter out addresses, gibberish, and invalid entries
        # More comprehensive address pattern
        address_patterns = [
            r'\d+\s+(?:W\.|E\.|N\.|S\.|WEST|EAST|NORTH|SOUTH)?\s*\w+\s+(?:ST\.|STREET|AVE\.|AVENUE|RD\.|ROAD|BLVD\.|BOULEVARD|DR\.|DRIVE|LANE|LN\.|WAY|COURT|CT\.|PLACE|PL\.)'
        ]
        
        filtered_orgs = []
        for org in result["organizations"]:
            is_invalid = False
            org_upper = org.upper()
            org_clean = org.replace('_', '').replace('-', '').replace(' ', '')
            
            # Check against address patterns
            for addr_pattern in address_patterns:
                if re.search(addr_pattern, org_upper, re.IGNORECASE):
                    is_invalid = True
                    break
            
            # Check if it looks like a street address (contains numbers and street words)
            if re.search(r'\d+.*(?:SUMMIT|STREET|AVENUE|ROAD)', org_upper):
                is_invalid = True
            
            # Check for gibberish patterns:
            # 1. Single character segments separated by underscores (like I_l_l_l_a_l_l_l_e)
            segments = org.replace('-', '_').split('_')
            single_char_segments = sum(1 for seg in segments if len(seg) == 1)
            if len(segments) > 3 and single_char_segments > len(segments) * 0.5:
                is_invalid = True
            
            # 2. Too many underscores or hyphens overall
            if org.count('_') > 3 or org.count('-') > 3:
                is_invalid = True
            
            # 3. Alternating single characters (I_l_l_l pattern)
            if re.match(r'^[a-zA-Z](_[a-zA-Z]){3,}$', org):
                is_invalid = True
            
            # 4. Excessive character repetition (more than 40% of chars are the same letter)
            if len(org_clean) > 0:
                char_counts = {}
                for char in org_clean.lower():
                    char_counts[char] = char_counts.get(char, 0) + 1
                max_char_ratio = max(char_counts.values()) / len(org_clean) if char_counts else 0
                if max_char_ratio > 0.4:
                    is_invalid = True
            
            # 5. Very short organizations (less than 3 chars, likely fragments)
            if len(org.replace('_', '').replace('-', '').strip()) < 3:
                is_invalid = True
            
            # 6. Contains mostly non-alphanumeric characters
            alpha_count = sum(1 for c in org if c.isalnum())
            if len(org) > 0 and alpha_count / len(org) < 0.5:
                is_invalid = True
            
            # 7. Contains mostly single-letter "words" (OCR artifact)
            words = org.replace('_', ' ').replace('-', ' ').split()
            single_letter_words = sum(1 for word in words if len(word) == 1)
            if len(words) > 2 and single_letter_words > len(words) * 0.6:
                is_invalid = True
            
            if not is_invalid:
                filtered_orgs.append(org)
        
        result["organizations"] = filtered_orgs
        
        # Whitelist filter for names - only keep allowed family names
        allowed_names = ["Mark", "Christine", "Mark & Christine", "Mackenzie", "Morgan"]
        filtered_names = []
        for name in result["names"]:
            # Only keep if it's exactly one of the allowed names (case-insensitive match)
            for allowed in allowed_names:
                if name.lower() == allowed.lower() or allowed.lower() in name.lower():
                    if allowed not in filtered_names:
                        filtered_names.append(allowed)
                    break
        
        result["names"] = filtered_names
        
        # Sort dates (most recent first)
        result["dates"].sort(reverse=True)
        
        return result
    
    def generate_filename_from_content(self, analysis: Dict[str, any], original_name: str) -> str:
        """
        Generate a suggested filename based on content analysis
        Format: Organization-for_Name-Date.pdf or Name-Date.pdf
        
        Args:
            analysis: Dictionary from analyze_pdf_content
            original_name: Original filename
            
        Returns:
            Suggested filename
        """
        parts = []
        person_part = None
        
        # Extract and clean organization name
        if analysis["organizations"]:
            org = analysis["organizations"][0]
            # First, normalize all whitespace (including newlines, tabs, carriage returns) to single spaces
            org = re.sub(r'\s+', ' ', org)
            # Remove uncommon punctuation and special characters
            # Keep only alphanumeric, spaces, hyphens, and underscores
            org = re.sub(r'[?&#@!$%^*+=\[\]{}()<>:;"\',./\\|`~]', '', org)
            # Replace spaces with underscores and strip leading/trailing whitespace
            org = org.strip().replace(' ', '_')
            parts.append(org)
        
        # Extract and prepare person name (to be added after organization)
        if analysis["names"]:
            name = analysis["names"][0]
            # First, normalize all whitespace (including newlines, tabs, carriage returns) to single spaces
            name = re.sub(r'\s+', ' ', name)
            # Remove uncommon punctuation and special characters
            name = re.sub(r'[?&#@!$%^*+=\[\]{}()<>:;"\',./\\|`~]', '', name)
            # Replace spaces with underscores and strip leading/trailing whitespace
            name = name.strip().replace(' ', '_')
            # Extract first name only for brevity
            first_name = name.split('_')[0] if '_' in name else name
            person_part = f"for_{first_name}"
        
        # Add person name after organization (if org exists) or as main part (if no org)
        if person_part:
            if parts:  # We have an organization
                parts.append(person_part)
            else:  # No organization, use person as main identifier
                parts.append(person_part.replace('for_', ''))
        
        # Add the most recent date at the end
        if analysis["dates"]:
            parts.append(analysis["dates"][0])
        
        # If we have parts, create the filename
        if parts:
            suggested_name = "-".join(parts) + ".pdf"
        else:
            # Fall back to original name with a prefix
            suggested_name = "renamed_" + original_name
        
        # Clean up the filename
        suggested_name = re.sub(r'[<>:"/\\|?*]', '', suggested_name)
        
        return suggested_name
    
    def rename_pdf_from_content(self, pdf_path: str, new_name: str = None, dry_run: bool = False) -> Tuple[bool, str, Dict]:
        """
        Rename a PDF file based on its content
        
        Args:
            pdf_path: Path to the PDF file
            new_name: Optional custom name to use (if None, will auto-generate)
            dry_run: If True, only return suggestions without renaming
            
        Returns:
            tuple: (success: bool, message: str, analysis: dict with suggested name)
        """
        if not PYMUPDF_AVAILABLE:
            return False, "PyMuPDF library not available", {}
        
        if not os.path.exists(pdf_path):
            return False, f"File not found: {pdf_path}", {}
        
        # Analyze content
        self.log(f"Analyzing content of {os.path.basename(pdf_path)}...")
        analysis = self.analyze_pdf_content(pdf_path)
        
        # Generate suggested filename
        original_name = os.path.basename(pdf_path)
        suggested_name = self.generate_filename_from_content(analysis, original_name)
        
        analysis["suggested_name"] = suggested_name
        
        if dry_run:
            return True, f"Suggested name: {suggested_name}", analysis
        
        # Use custom name if provided, otherwise use suggested
        final_name = new_name if new_name else suggested_name
        
        # Build new path
        directory = os.path.dirname(pdf_path)
        new_path = os.path.join(directory, final_name)
        
        # Check if file already exists
        if os.path.exists(new_path) and new_path != pdf_path:
            return False, f"File already exists: {final_name}", analysis
        
        # Rename the file
        try:
            os.rename(pdf_path, new_path)
            
            # Update internal references
            if pdf_path in self.loaded_pdfs:
                idx = self.loaded_pdfs.index(pdf_path)
                self.loaded_pdfs[idx] = new_path
            
            # Update page references
            self.pdf_pages = [(idx, page, new_path if path == pdf_path else path) 
                             for idx, page, path in self.pdf_pages]
            
            # Update current preview
            if self.current_preview_pdf == pdf_path:
                self.current_preview_pdf = new_path
            
            self.log(f"Renamed: {original_name} → {final_name}")
            return True, f"Successfully renamed to: {final_name}", analysis
            
        except Exception as e:
            self.log(f"Error renaming file: {str(e)}", logging.ERROR)
            return False, f"Error renaming file: {str(e)}", analysis


def main(page: ft.Page):
    """Main Flet application"""
    logger.info("Starting Flet application")
    page.title = "📄 PDFUtils - PDF Management Tool"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    
    # Set window size
    page.window.height = 900
    page.window.width = 1000
    page.window.resizable = True
    
    page.scroll = ft.ScrollMode.AUTO
    
    # Initialize persistent storage
    storage = PersistentStorage()
    logger.info("Persistent storage initialized")
    
    # Log display list
    log_messages = []
    
    # UI Components
    status_text = ft.Text("", color=ft.Colors.BLUE)
    
    # Log output window
    log_output = ft.ListView(
        spacing=2,
        padding=10,
        auto_scroll=True,
        height=100,
    )
    
    def add_log_message(message: str):
        """Add a message to the log output window"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        log_messages.append(log_msg)
        log_output.controls.append(
            ft.Text(log_msg, size=11, color=ft.Colors.GREY_800)
        )
        if len(log_messages) > 100:
            log_messages.pop(0)
            log_output.controls.pop(0)
        page.update()
    
    # Initialize PDF manager with log callback
    pdf_manager = PDFManager(log_callback=add_log_message)
    
    add_log_message("PDFUtils started")
    add_log_message(f"Log file: {log_filename}")
    
    if not PYMUPDF_AVAILABLE:
        add_log_message("WARNING: PyMuPDF not installed - PDF operations limited")
    
    def update_status(message: str, is_error: bool = False):
        """Update status message"""
        status_text.value = message
        status_text.color = ft.Colors.RED if is_error else ft.Colors.GREEN
        add_log_message(f"Status: {message}")
        page.update()
    
    # PDF files list view
    pdf_list = ft.ListView(
        spacing=5,
        padding=10,
        height=150,
    )
    
    # Page order list (for reordering)
    page_order_list = ft.ListView(
        spacing=5,
        padding=10,
        height=250,
    )
    
    # PDF preview image
    preview_image = ft.Image(
        src="",
        width=400,
        height=500,
        fit=ft.ImageFit.CONTAIN,
        visible=False,
    )
    
    preview_page_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
    
    # Current preview state
    current_preview_index = 0
    
    def update_pdf_list():
        """Update the PDF files list display"""
        pdf_list.controls.clear()
        
        pdf_infos = pdf_manager.get_loaded_pdf_info()
        if not pdf_infos:
            pdf_list.controls.append(
                ft.Text("No PDFs loaded", italic=True, color=ft.Colors.GREY_600)
            )
        else:
            for i, info in enumerate(pdf_infos):
                pdf_list.controls.append(
                    ft.Row([
                        ft.Icon(ft.Icons.PICTURE_AS_PDF, color=ft.Colors.RED_700),
                        ft.Text(f"{info['name']} ({info['page_count']} pages)", expand=True),
                        ft.IconButton(
                            icon=ft.Icons.VISIBILITY,
                            tooltip="Preview",
                            on_click=lambda e, path=info['path']: preview_pdf(path),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            tooltip="Remove",
                            icon_color=ft.Colors.RED_700,
                            on_click=lambda e, idx=i: remove_pdf(idx),
                        ),
                    ], spacing=5)
                )
        page.update()
    
    def update_page_order_list():
        """Update the page order list display"""
        page_order_list.controls.clear()
        
        if not pdf_manager.pdf_pages:
            page_order_list.controls.append(
                ft.Text("No pages loaded", italic=True, color=ft.Colors.GREY_600)
            )
        else:
            for i, (pdf_idx, page_num, pdf_path) in enumerate(pdf_manager.pdf_pages):
                pdf_name = os.path.basename(pdf_path)
                page_order_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(f"{i + 1}.", width=30),
                            ft.Icon(ft.Icons.DESCRIPTION, size=20),
                            ft.Text(f"{pdf_name} - Page {page_num + 1}", expand=True, size=12),
                            ft.IconButton(
                                icon=ft.Icons.ARROW_UPWARD,
                                tooltip="Move up",
                                on_click=lambda e, idx=i: move_page_up(idx),
                                disabled=(i == 0),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.ARROW_DOWNWARD,
                                tooltip="Move down",
                                on_click=lambda e, idx=i: move_page_down(idx),
                                disabled=(i == len(pdf_manager.pdf_pages) - 1),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.REMOVE_CIRCLE,
                                tooltip="Remove page",
                                icon_color=ft.Colors.RED_700,
                                on_click=lambda e, idx=i: remove_single_page(idx),
                            ),
                        ], spacing=2),
                        padding=5,
                        bgcolor=ft.Colors.GREY_100,
                        border_radius=5,
                    )
                )
        page.update()
    
    def move_page_up(index: int):
        """Move a page up in the order"""
        if index > 0:
            pdf_manager.move_page(index, index - 1)
            update_page_order_list()
    
    def move_page_down(index: int):
        """Move a page down in the order"""
        if index < len(pdf_manager.pdf_pages) - 1:
            pdf_manager.move_page(index, index + 1)
            update_page_order_list()
    
    def remove_single_page(index: int):
        """Remove a single page from the order"""
        pdf_manager.remove_page(index)
        update_page_order_list()
        update_status(f"Page removed. {len(pdf_manager.pdf_pages)} pages remaining.")
    
    def remove_pdf(pdf_index: int):
        """Remove a PDF and all its pages"""
        if 0 <= pdf_index < len(pdf_manager.loaded_pdfs):
            pdf_path = pdf_manager.loaded_pdfs[pdf_index]
            pdf_manager.loaded_pdfs.pop(pdf_index)
            # Remove all pages from this PDF
            pdf_manager.pdf_pages = [p for p in pdf_manager.pdf_pages if p[2] != pdf_path]
            update_pdf_list()
            update_page_order_list()
            update_status(f"Removed PDF and its pages")
    
    def preview_pdf(pdf_path: str, page_num: int = 0):
        """Preview a PDF page"""
        nonlocal current_preview_index
        
        if not PYMUPDF_AVAILABLE:
            update_status("PyMuPDF not available for preview", True)
            return
        
        pdf_manager.current_preview_pdf = pdf_path
        pdf_manager.current_preview_page = page_num
        current_preview_index = page_num
        
        page_count = pdf_manager.get_pdf_page_count(pdf_path)
        img_path = pdf_manager.render_pdf_page_to_image(pdf_path, page_num, zoom=1.5)
        
        if img_path and os.path.exists(img_path):
            preview_image.src = img_path
            preview_image.visible = True
            preview_page_text.value = f"Page {page_num + 1} of {page_count} - {os.path.basename(pdf_path)}"
            page.update()
    
    def prev_preview_page(e):
        """Show previous page in preview"""
        nonlocal current_preview_index
        if pdf_manager.current_preview_pdf and current_preview_index > 0:
            current_preview_index -= 1
            preview_pdf(pdf_manager.current_preview_pdf, current_preview_index)
    
    def next_preview_page(e):
        """Show next page in preview"""
        nonlocal current_preview_index
        if pdf_manager.current_preview_pdf:
            page_count = pdf_manager.get_pdf_page_count(pdf_manager.current_preview_pdf)
            if current_preview_index < page_count - 1:
                current_preview_index += 1
                preview_pdf(pdf_manager.current_preview_pdf, current_preview_index)
    
    # File picker for opening PDFs
    def on_files_picked(e: ft.FilePickerResultEvent):
        if e.files:
            file_paths = [f.path for f in e.files if f.path]
            if file_paths:
                storage.record_function_usage("open_pdfs")
                success, message = pdf_manager.load_pdf_files(file_paths)
                update_pdf_list()
                update_page_order_list()
                update_status(message, not success)
                
                # Auto-preview first loaded PDF
                if pdf_manager.loaded_pdfs:
                    preview_pdf(pdf_manager.loaded_pdfs[-1])
    
    file_picker = ft.FilePicker(on_result=on_files_picked)
    page.overlay.append(file_picker)
    
    # Save file picker for merge output
    def on_save_picked(e: ft.FilePickerResultEvent):
        if e.path:
            output_path = e.path
            if not output_path.lower().endswith('.pdf'):
                output_path += '.pdf'
            
            storage.record_function_usage("merge_pdfs")
            success, message = pdf_manager.merge_pdfs(output_path)
            update_status(message, not success)
    
    save_picker = ft.FilePicker(on_result=on_save_picked)
    page.overlay.append(save_picker)
    
    # PNG export file picker
    def on_png_export_picked(e: ft.FilePickerResultEvent):
        if e.path:
            output_path = e.path
            if not output_path.lower().endswith('.png'):
                output_path += '.png'
            
            storage.record_function_usage("export_page_to_png")
            
            # Use the current preview page
            if not pdf_manager.current_preview_pdf:
                update_status("No PDF page selected", True)
                return
            
            success, message = pdf_manager.export_page_to_png(
                pdf_manager.current_preview_pdf, 
                current_preview_index,
                output_path,
                dpi=300
            )
            update_status(message, not success)
    
    png_export_picker = ft.FilePicker(on_result=on_png_export_picked)
    page.overlay.append(png_export_picker)
    
    def on_open_files_click(e):
        """Handle Open Files button click"""
        file_picker.pick_files(
            allow_multiple=True,
            allowed_extensions=["pdf"],
            dialog_title="Select PDF Files"
        )
    
    def on_clear_all_click(e):
        """Handle Clear All button click"""
        pdf_manager.clear_all_pdfs()
        update_pdf_list()
        update_page_order_list()
        preview_image.visible = False
        preview_page_text.value = ""
        update_status("All PDFs cleared")
    
    def on_merge_click(e):
        """Handle Merge button click"""
        if not pdf_manager.pdf_pages:
            update_status("No pages to merge", True)
            return
        
        save_picker.save_file(
            allowed_extensions=["pdf"],
            dialog_title="Save Merged PDF As",
            file_name="merged_output.pdf"
        )
    
    def on_print_click(e):
        """Handle Print button click"""
        storage.record_function_usage("print_pdf")
        
        if not pdf_manager.current_preview_pdf:
            update_status("No PDF selected for printing", True)
            return
        
        success, message = pdf_manager.print_pdf(pdf_manager.current_preview_pdf)
        update_status(message, not success)
    
    def on_print_merged_click(e):
        """Print the merged PDF (merges to temp file first)"""
        storage.record_function_usage("print_merged")
        
        if not pdf_manager.pdf_pages:
            update_status("No pages to print", True)
            return
        
        # Merge to temp file first
        temp_output = os.path.join(pdf_manager.temp_dir, "merged_print.pdf")
        success, message = pdf_manager.merge_pdfs(temp_output)
        
        if success:
            success, message = pdf_manager.print_pdf(temp_output)
        
        update_status(message, not success)
    
    def on_export_png_click(e):
        """Handle Export to PNG button click"""
        if not pdf_manager.current_preview_pdf:
            update_status("No PDF page selected to export", True)
            return
        
        # Get the PDF filename and page number for default filename
        pdf_name = os.path.splitext(os.path.basename(pdf_manager.current_preview_pdf))[0]
        default_filename = f"{pdf_name}_page_{current_preview_index + 1}.png"
        
        png_export_picker.save_file(
            allowed_extensions=["png"],
            dialog_title="Export Page to PNG",
            file_name=default_filename
        )
    
    def on_rename_from_content_click(e):
        """Handle Rename from Content button click"""
        storage.record_function_usage("rename_from_content")
        
        if not pdf_manager.loaded_pdfs:
            update_status("No PDFs loaded to rename", True)
            return
        
        # Show dialog to select which PDFs to rename
        show_rename_dialog()
    
    def on_function_selected(e):
        """Handle function selection from dropdown"""
        selected_function = e.control.value
        
        # Map function names to their handlers
        function_handlers = {
            "merge_pdfs": on_merge_click,
            "print_pdf": on_print_click,
            "print_merged": on_print_merged_click,
            "export_page_to_png": on_export_png_click,
            "rename_from_content": on_rename_from_content_click,
        }
        
        # Execute the selected function
        if selected_function in function_handlers:
            function_handlers[selected_function](e)
        
        # Reset dropdown to show placeholder
        e.control.value = None
        page.update()
    
    def show_rename_dialog():
        """Show dialog for renaming PDFs based on content"""
        
        # Get all loaded PDFs
        pdf_infos = pdf_manager.get_loaded_pdf_info()
        
        if not pdf_infos:
            update_status("No PDFs loaded", True)
            return
        
        # Create checkbox list for PDF selection
        pdf_checkboxes = []
        for info in pdf_infos:
            checkbox = ft.Checkbox(
                label=info['name'],
                value=True,
                data=info['path']
            )
            pdf_checkboxes.append(checkbox)
        
        # Preview area for suggestions (using Column for scrollability)
        preview_column = ft.Column(
            [ft.Text("Select PDFs and click 'Analyze' to see suggested names", 
                    size=12, 
                    color=ft.Colors.GREY_700)],
            spacing=5,
            scroll=ft.ScrollMode.AUTO,
        )
        
        analysis_results = {}
        
        def analyze_selected(e):
            """Analyze selected PDFs and show suggestions"""
            selected_paths = [cb.data for cb in pdf_checkboxes if cb.value]
            
            preview_column.controls.clear()
            
            if not selected_paths:
                preview_column.controls.append(
                    ft.Text("No PDFs selected", size=12, color=ft.Colors.GREY_700)
                )
                page.update()
                return
            
            preview_column.controls.append(
                ft.Text("Suggested names:", size=13, weight=ft.FontWeight.BOLD)
            )
            
            analysis_results.clear()
            
            for pdf_path in selected_paths:
                success, message, analysis = pdf_manager.rename_pdf_from_content(
                    pdf_path, 
                    dry_run=True
                )
                
                if success and analysis.get("suggested_name"):
                    original = os.path.basename(pdf_path)
                    suggested = analysis["suggested_name"]
                    analysis_results[pdf_path] = analysis
                    
                    # Add original filename
                    preview_column.controls.append(
                        ft.Text(f"• {original}", size=12, weight=ft.FontWeight.BOLD)
                    )
                    
                    # Add suggested filename
                    preview_column.controls.append(
                        ft.Text(f"  → {suggested}", size=12, color=ft.Colors.BLUE_700)
                    )
                    
                    # Show what was found
                    found_items = []
                    if analysis.get("dates"):
                        found_items.append(f"Dates: {', '.join(analysis['dates'][:2])}")
                    if analysis.get("organizations"):
                        found_items.append(f"Orgs: {', '.join(analysis['organizations'][:2])}")
                    if analysis.get("names"):
                        found_items.append(f"Names: {', '.join(analysis['names'][:2])}")
                    
                    if found_items:
                        preview_column.controls.append(
                            ft.Text(f"  ({'; '.join(found_items)})", 
                                   size=11, 
                                   color=ft.Colors.GREY_600,
                                   italic=True)
                        )
                    
                    # Add spacing between entries
                    preview_column.controls.append(ft.Container(height=10))
            
            if not analysis_results:
                preview_column.controls.clear()
                preview_column.controls.append(
                    ft.Text("No content found to generate names", 
                           size=12, 
                           color=ft.Colors.ORANGE_700)
                )
            
            page.update()
        
        def confirm_rename(e):
            """Perform the actual rename operation"""
            selected_paths = [cb.data for cb in pdf_checkboxes if cb.value]
            
            if not selected_paths:
                update_status("No PDFs selected", True)
                rename_dialog.open = False
                page.update()
                return
            
            success_count = 0
            failed_count = 0
            
            for pdf_path in selected_paths:
                analysis = analysis_results.get(pdf_path)
                if analysis and analysis.get("suggested_name"):
                    success, message, _ = pdf_manager.rename_pdf_from_content(
                        pdf_path,
                        new_name=analysis["suggested_name"],
                        dry_run=False
                    )
                    
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
            
            # Update UI
            update_pdf_list()
            update_page_order_list()
            
            rename_dialog.open = False
            page.update()
            
            if failed_count == 0:
                update_status(f"Successfully renamed {success_count} file(s)")
            else:
                update_status(f"Renamed {success_count} file(s), {failed_count} failed", True)
        
        def close_dialog(e):
            rename_dialog.open = False
            page.update()
        
        # Create dialog
        rename_dialog = ft.AlertDialog(
            title=ft.Text("🏷️ Rename PDFs from Content"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Select PDFs to rename based on their content:", 
                           size=14, 
                           weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=ft.Column(
                            pdf_checkboxes,
                            spacing=5,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        height=200,
                    ),
                    ft.Divider(),
                    ft.Container(
                        content=preview_column,
                        padding=10,
                        bgcolor=ft.Colors.GREY_100,
                        border_radius=5,
                        height=200,
                    ),
                ], spacing=10),
                width=600,
            ),
            actions=[
                ft.TextButton("Analyze", on_click=analyze_selected),
                ft.TextButton("Rename", on_click=confirm_rename),
                ft.TextButton("Cancel", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        page.overlay.append(rename_dialog)
        rename_dialog.open = True
        page.update()
    
    # Cleanup on page close
    def on_window_close(e):
        pdf_manager.cleanup()
    
    page.on_close = on_window_close
    
    # Helper function to get sorted functions by usage
    def get_sorted_functions():
        """Get functions sorted by last used time"""
        # Available active functions
        active_functions = [
            "merge_pdfs",
            "print_pdf", 
            "print_merged",
            "export_page_to_png",
            "rename_from_content",
        ]
        
        # Get usage data and sort
        function_usage = []
        for func_name in active_functions:
            usage = storage.get_function_usage(func_name)
            last_used = usage.get("last_used")
            function_usage.append({
                "name": func_name,
                "last_used": last_used,
                "count": usage.get("count", 0)
            })
        
        # Sort by last_used (None values go to end), then by name
        function_usage.sort(key=lambda x: (x["last_used"] is None, x["last_used"] or ""), reverse=True)
        
        return function_usage
    
    # Function definitions with metadata for future extensibility.
    # This dictionary documents available and planned functions.
    # Used with storage.record_function_usage() to track usage patterns.
    available_functions = {
        "open_pdfs": {
            "label": "Open PDF Files",
            "icon": "📂",
            "description": "Open one or more PDF files"
        },
        "merge_pdfs": {
            "label": "Merge PDFs",
            "icon": "🔗",
            "description": "Merge loaded PDFs into a single file"
        },
        "print_pdf": {
            "label": "Print PDF",
            "icon": "🖨️",
            "description": "Print the currently selected PDF"
        },
        "print_merged": {
            "label": "Print Merged",
            "icon": "🖨️",
            "description": "Merge and print all pages"
        },
        "export_page_to_png": {
            "label": "Export Page to PNG",
            "icon": "🖼️",
            "description": "Export current page to PNG image"
        },
        "rename_from_content": {
            "label": "Rename from Content",
            "icon": "🏷️",
            "description": "Rename PDFs based on dates, names, and organizations found in content"
        },
        # Placeholder functions for future expansion
        "rotate_pages": {
            "label": "Rotate Pages",
            "icon": "🔄",
            "description": "Rotate selected pages"
        },
        "extract_pages": {
            "label": "Extract Pages",
            "icon": "📤",
            "description": "Extract pages to a new PDF"
        },
        "split_pdf": {
            "label": "Split PDF",
            "icon": "✂️",
            "description": "Split PDF into multiple files"
        },
        "compress_pdf": {
            "label": "Compress PDF",
            "icon": "📦",
            "description": "Compress PDF to reduce file size"
        },
    }
    
    # Build UI
    page.add(
        ft.Column([
            # Header
            ft.Text("📄 PDFUtils - PDF Management Tool", 
                   size=24, 
                   weight=ft.FontWeight.BOLD),
            ft.Text("Open, display, reorder, merge, print, and smartly rename PDF files",
                   size=14,
                   color=ft.Colors.GREY_700),
            ft.Divider(height=5),
            
            # Main content area - two columns
            ft.Row([
                # Left column - Controls and lists
                ft.Column([
                    # File Operations section
                    ft.Container(
                        content=ft.Column([
                            ft.Text("File Operations", size=16, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                ft.ElevatedButton(
                                    "📂 Open PDFs",
                                    on_click=on_open_files_click,
                                    icon=ft.Icons.FOLDER_OPEN,
                                ),
                                ft.ElevatedButton(
                                    "🗑️ Clear All",
                                    on_click=on_clear_all_click,
                                    icon=ft.Icons.CLEAR_ALL,
                                ),
                            ], spacing=10),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=10,
                    ),
                    
                    # Loaded PDFs section
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Loaded PDFs", size=16, weight=ft.FontWeight.BOLD),
                            ft.Container(
                                content=pdf_list,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=5,
                                bgcolor=ft.Colors.WHITE,
                            ),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=10,
                    ),
                    
                    # Page Order section
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Text("Page Order", size=16, weight=ft.FontWeight.BOLD, expand=True),
                                ft.Text(f"{len(pdf_manager.pdf_pages)} pages", size=12, color=ft.Colors.GREY_600),
                            ]),
                            ft.Container(
                                content=page_order_list,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=5,
                                bgcolor=ft.Colors.WHITE,
                            ),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=10,
                    ),
                    
                    # Operations section with dropdown
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Operations", size=16, weight=ft.FontWeight.BOLD),
                            ft.Dropdown(
                                label="Select an operation",
                                hint_text="Choose a function to execute...",
                                width=400,
                                on_change=on_function_selected,
                                options=[
                                    ft.dropdown.Option(
                                        key=func["name"],
                                        text=f"{available_functions[func['name']]['icon']} {available_functions[func['name']]['label']}" + 
                                             (f" (used {func['count']}x)" if func['count'] > 0 else "")
                                    ) for func in get_sorted_functions()
                                ],
                            ),
                            ft.Text(
                                "Functions are ordered by most recently used",
                                size=11,
                                color=ft.Colors.GREY_600,
                                italic=True,
                            ),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=10,
                    ),
                ], width=450, spacing=10),
                
                # Right column - Preview
                ft.Column([
                    ft.Container(
                        content=ft.Column([
                            ft.Text("PDF Preview", size=16, weight=ft.FontWeight.BOLD),
                            preview_page_text,
                            ft.Row([
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    tooltip="Previous page",
                                    on_click=prev_preview_page,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_FORWARD,
                                    tooltip="Next page",
                                    on_click=next_preview_page,
                                ),
                            ], alignment=ft.MainAxisAlignment.CENTER),
                            ft.Container(
                                content=preview_image,
                                border=ft.border.all(1, ft.Colors.GREY_300),
                                border_radius=5,
                                bgcolor=ft.Colors.GREY_200,
                                alignment=ft.alignment.center,
                                padding=10,
                            ),
                        ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=10,
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=10,
                        expand=True,
                    ),
                ], expand=True, spacing=10),
            ], spacing=20, vertical_alignment=ft.CrossAxisAlignment.START),
            
            ft.Divider(height=5),
            
            # Status section
            ft.Container(
                content=ft.Column([
                    ft.Text("Status", size=14, weight=ft.FontWeight.BOLD),
                    status_text,
                ], spacing=5),
                padding=5,
            ),
            
            # Log output section
            ft.Container(
                content=ft.Column([
                    ft.Text("Log Output", size=14, weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=log_output,
                        border=ft.border.all(1, ft.Colors.GREY_400),
                        border_radius=5,
                        bgcolor=ft.Colors.GREY_100,
                    ),
                ], spacing=5),
                padding=5,
            ),
        ], spacing=10)
    )
    
    # Initialize lists
    update_pdf_list()
    update_page_order_list()
    
    logger.info("UI initialized successfully")


if __name__ == "__main__":
    logger.info("PDFUtils starting...")
    ft.app(
        target=main,
        assets_dir="assets",
    )
