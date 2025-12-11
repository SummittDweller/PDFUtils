# 📄 PDFUtils - PDF Management Tool

A Flet-based desktop application for PDF management. Open, display, reorder, merge, and print PDF files with an intuitive user interface.

**PDFUtils** provides a user-friendly interface for common PDF operations, with an extensible architecture for future enhancements.

## Features

### Current Features

1. **Open Multiple PDFs** - Load one or more PDF files at once
2. **PDF Preview** - View PDF pages with page navigation
3. **Page Reordering** - Rearrange pages from multiple PDFs using up/down controls
4. **Merge PDFs** - Combine pages from multiple PDFs into a single output file
5. **Print PDF** - Print the currently selected PDF or the merged result
6. **Export to PNG** - Export the current page to a high-resolution PNG image (300 DPI)
7. **Remove Pages** - Remove individual pages or entire PDFs from the merge list
8. **Rename from Content** - Intelligently rename PDF files based on content by extracting dates, personal names, and service provider names from the document

### Planned Features (Coming Soon)

- **Rotate Pages** - Rotate selected pages 90°, 180°, or 270°
- **Extract Pages** - Extract specific pages to a new PDF
- **Split PDF** - Split a PDF into multiple files
- **Compress PDF** - Reduce PDF file size

## Technology Stack

- **[Flet](https://flet.dev)** - Modern Python framework for building cross-platform desktop/web UIs
- **[PyMuPDF](https://pymupdf.readthedocs.io/)** - Fast PDF rendering and manipulation library
- **Python 3.x** - Programming language

## Project Structure

```
PDFUtils/
├── app.py              # Main Flet application
├── requirements.txt    # Python dependencies
├── run.sh              # Quick launch script (Linux/macOS)
├── assets/             # Static assets directory
├── logfiles/           # Application log files directory
├── .gitignore          # Git ignore rules
├── LICENSE             # License file
└── README.md           # This file
```

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/SummittDweller/PDFUtils.git
   cd PDFUtils
   ```

2. **Run the application**
   
   **On Linux/macOS:**
   ```bash
   ./run.sh
   ```
   
   The script will:
   - Create a virtual environment (`.venv`) if it doesn't exist
   - Install all required dependencies
   - Launch the PDFUtils application

### Manual Installation (Alternative)

If you prefer to set up manually or are on Windows:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## Usage

### Opening PDF Files

1. Click the **"📂 Open PDFs"** button
2. Select one or more PDF files from the file dialog
3. The files will be loaded and displayed in the "Loaded PDFs" list

### Previewing PDFs

- Click the **👁️ (eye icon)** next to any loaded PDF to preview it
- Use the **◀ ▶** navigation buttons to move between pages

### Reordering Pages

The "Page Order" section shows all pages from all loaded PDFs:
- Use the **⬆ ⬇** arrows to move pages up or down
- Click the **🔴 remove** icon to remove individual pages
- Pages will be merged in the order shown

### Merging PDFs

1. Load the desired PDF files
2. Reorder pages as needed
3. Click **"🔗 Merge & Save"**
4. Choose a location and filename for the merged PDF

### Printing

- **Print Current** - Prints the currently previewed PDF
- **Print Merged** - Merges all pages first, then prints the result

### Exporting to PNG

1. Preview the page you want to export
2. Click **"🖼️ Export to PNG"**
3. Choose a location and filename for the PNG image
4. The page will be exported at 300 DPI resolution for high quality

### Renaming from Content

The "Rename from Content" feature intelligently analyzes PDF content and suggests filenames based on:
- **Dates** - Extracts dates in various formats (MM/DD/YYYY, YYYY-MM-DD, Month DD YYYY, etc.)
- **Personal Names** - Identifies people's names using Named Entity Recognition (when spaCy is installed)
- **Service Providers** - Detects common organizations like banks, insurance companies, utilities, and tech companies

**To use this feature:**

1. Load one or more PDF files
2. Click **"🏷️ Rename from Content"**
3. Select which PDFs to analyze (all are selected by default)
4. Click **"Analyze"** to see suggested filenames
5. Review the suggestions and click **"Rename"** to apply

**Suggested filename format:** `YYYY-MM-DD_Organization_Name.pdf`

**Note:** For best results with name extraction, install the spaCy English model:
```bash
python -m spacy download en_core_web_sm
```

## Dependencies

See `requirements.txt` for complete list:
- `flet==0.27.1` - UI framework (pinned to 0.27.1 for macOS/Python 3.14 compatibility)
- `PyMuPDF>=1.24.0` - PDF handling library
- `python-dotenv>=1.0.0` - Environment variable management
- `spacy>=3.7.0` - Natural Language Processing for Named Entity Recognition
- `python-dateutil>=2.8.0` - Advanced date parsing

**Note:** Flet is pinned to version 0.27.1 due to compatibility issues with file picker dialogs on macOS and Python 3.14 in newer versions.

## Architecture

The application follows a clean separation of concerns:

- **`PDFManager` class** - Handles all PDF operations (loading, merging, rendering, printing)
- **`PersistentStorage` class** - Manages UI state persistence
- **`main()` function** - Builds the Flet UI and handles user interactions

### Adding New Functions

To add new PDF operations:

1. Add a method to the `PDFManager` class:
   ```python
   def rotate_pages(self, pages: list, angle: int) -> tuple[bool, str]:
       """Rotate selected pages by the specified angle"""
       # Implementation here
       return True, "Success message"
   ```

2. Create an event handler in `main()`:
   ```python
   def on_rotate_click(e):
       storage.record_function_usage("rotate_pages")
       # Call the PDFManager method
   ```

3. Add a button to the UI

4. Update the `functions` dictionary for future extensibility tracking

## Development

### Logging

- Logs are written to timestamped files in the `logfiles/` directory: `logfiles/pdfutils_YYYYMMDD_HHMMSS.log`
- The log output window in the UI shows real-time operation details
- Set `logging.DEBUG` for verbose output during development

### Temporary Files

- PDF page previews are rendered to a temporary directory
- The temp directory is automatically cleaned up when the application closes
- Manual cleanup occurs in the `PDFManager.cleanup()` method

## Troubleshooting

### "PyMuPDF not installed" warning
- Run: `pip install PyMuPDF`
- Ensure you're using the correct Python environment

### PDF preview not showing
- Ensure PyMuPDF is properly installed
- Check that the PDF file is valid and not corrupted
- Look at the log output for error messages

### Print not working
- **macOS**: PDFs open in Preview for printing with full print dialog access
- **Linux**: Ensure `lpr` is installed and configured
- **Windows**: PDF should open in the default PDF viewer with print dialog
- Check that you have a printer configured on your system

## Related Tools

### ScanRenamer Background Application

A companion background application that automatically renames scanned PDF files with timestamps when they appear in a watched folder.

**Application Location:**
- `~/Applications/ScanRenamer.app` - Standalone macOS application that runs at startup

**Setup Files:**
- `~/Desktop/SCANRENAMER-APP-INSTRUCTIONS.txt` - Complete setup and usage instructions
- `~/Desktop/rename-scan-instructions.md` - Detailed documentation with alternative solutions

**What It Does:**
- Runs invisibly in the background
- Monitors `~/Desktop/Recently-Scanned` folder every 2 seconds
- Automatically renames any file named `Scan.pdf` to `Scan_YYYY-MM-DD_HHMMSS.pdf`
- Logs all activity to `~/Library/Logs/ScanRenamer.log`

**Quick Setup:**
1. Open System Settings → General → Login Items
2. Click the "+" button under "Open at Login"
3. Navigate to your home folder → Applications
4. Select `ScanRenamer.app` and click "Open"
5. The app will now start automatically at login

**Manual Start/Stop:**
```bash
# Start the app
open ~/Applications/ScanRenamer.app

# Stop the app
pkill -f ScanRenamer

# View logs
tail -f ~/Library/Logs/ScanRenamer.log
```

**Testing:**
Copy a file named `Scan.pdf` to `~/Desktop/Recently-Scanned` and it will be automatically renamed within 2 seconds.

**Alternative Solutions:**
The `rename-scan-instructions.md` file also includes:
- Automator Folder Action workflow
- Manual Shortcuts workflow (run on demand)
- Python + launchd solution for continuous monitoring

## Acknowledgments

- Built with [Flet](https://flet.dev)
- PDF handling powered by [PyMuPDF](https://pymupdf.readthedocs.io/)
- Inspired by [CABB](https://github.com/Digital-Grinnell/CABB) application architecture

## License

See the [LICENSE](LICENSE) file for details.
