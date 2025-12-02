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
from datetime import datetime
from pathlib import Path

# Try to import PyMuPDF (fitz), provide fallback error message
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

# Configure logging
log_filename = f"pdfutils_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
PERSISTENCE_FILE = "pdfutils_persistent.json"


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
    
    def load_pdf_files(self, file_paths: list) -> tuple[bool, str]:
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
    
    def merge_pdfs(self, output_path: str) -> tuple[bool, str]:
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
    
    def print_pdf(self, pdf_path: str) -> tuple[bool, str]:
        """
        Print a PDF file using the system's default print mechanism
        
        Args:
            pdf_path: Path to the PDF file to print
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not os.path.exists(pdf_path):
            return False, f"File not found: {pdf_path}"
        
        self.log(f"Printing: {os.path.basename(pdf_path)}...")
        
        try:
            system = platform.system()
            
            if system == "Windows":
                # Use Windows print command
                os.startfile(pdf_path, "print")
                return True, f"Sent to print: {os.path.basename(pdf_path)}"
                
            elif system == "Darwin":  # macOS
                # Use lpr command on macOS
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
    
    # Cleanup on page close
    def on_window_close(e):
        pdf_manager.cleanup()
    
    page.on_close = on_window_close
    
    # Function definitions with metadata for future extensibility
    functions = {
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
            ft.Text("Open, display, reorder, merge, and print PDF files",
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
                                ft.Text("Page Order (Drag to Reorder)", size=16, weight=ft.FontWeight.BOLD, expand=True),
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
                    
                    # Merge & Print section
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Output Operations", size=16, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                ft.ElevatedButton(
                                    "🔗 Merge & Save",
                                    on_click=on_merge_click,
                                    icon=ft.Icons.MERGE,
                                    bgcolor=ft.Colors.BLUE_700,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.ElevatedButton(
                                    "🖨️ Print Current",
                                    on_click=on_print_click,
                                    icon=ft.Icons.PRINT,
                                ),
                                ft.ElevatedButton(
                                    "🖨️ Print Merged",
                                    on_click=on_print_merged_click,
                                    icon=ft.Icons.PRINT,
                                ),
                            ], spacing=10, wrap=True),
                        ], spacing=5),
                        padding=10,
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=10,
                    ),
                    
                    # Future Functions placeholder
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Additional Functions (Coming Soon)", size=16, weight=ft.FontWeight.BOLD),
                            ft.Row([
                                ft.ElevatedButton(
                                    "🔄 Rotate",
                                    disabled=True,
                                    tooltip="Coming soon",
                                ),
                                ft.ElevatedButton(
                                    "📤 Extract",
                                    disabled=True,
                                    tooltip="Coming soon",
                                ),
                                ft.ElevatedButton(
                                    "✂️ Split",
                                    disabled=True,
                                    tooltip="Coming soon",
                                ),
                                ft.ElevatedButton(
                                    "📦 Compress",
                                    disabled=True,
                                    tooltip="Coming soon",
                                ),
                            ], spacing=10, wrap=True),
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
