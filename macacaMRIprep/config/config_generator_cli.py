#!/usr/bin/env python3
"""
CLI tool to launch the macacaMRIprep configuration generator with dataset preview.

This script:
1. Takes a dataset_dir argument
2. Finds the first scan in the BIDS dataset
3. Generates a preview image
4. Launches the HTML config generator with the preview
"""

import argparse
import sys
import tempfile
import base64
import io
from pathlib import Path
import webbrowser
import http.server
import socketserver
import threading
import time

try:
    from bids import BIDSLayout
except ImportError:
    print("Error: pybids is not installed. Please install it with: pip install pybids")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    from macacaMRIprep.quality_control.mri_plotting import create_overlay_grid_3xN
except ImportError as e:
    print(f"Error importing plotting utilities: {e}")
    sys.exit(1)


def find_first_scan(dataset_dir: Path):
    """
    Find the first scan in a BIDS dataset.
    Priority: T1w > other anatomical > functional
    
    Args:
        dataset_dir: Path to BIDS dataset root
        
    Returns:
        Path to first NIfTI file found, or None
    """
    dataset_dir = Path(dataset_dir)
    
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")
    
    try:
        layout = BIDSLayout(str(dataset_dir), validate=False, derivatives=False)
    except Exception as e:
        print(f"Warning: Could not initialize BIDSLayout: {e}")
        print("Falling back to simple file search...")
        return find_first_scan_simple(dataset_dir)
    
    # Priority order: T1w > T2w > other anatomical > functional
    suffixes = ['T1w', 'T2w', 'bold']
    
    for suffix in suffixes:
        files = layout.get(suffix=suffix, extension=['.nii.gz', '.nii'], return_type='filename')
        if files:
            return Path(files[0])
    
    # If nothing found via BIDSLayout, try simple search
    return find_first_scan_simple(dataset_dir)


def find_first_scan_simple(dataset_dir: Path):
    """
    Simple file search fallback when BIDSLayout fails.
    
    Args:
        dataset_dir: Path to BIDS dataset root
        
    Returns:
        Path to first NIfTI file found, or None
    """
    # Search for NIfTI files in typical BIDS structure
    patterns = [
        '**/anat/*.nii.gz',
        '**/anat/*.nii',
        '**/func/*.nii.gz',
        '**/func/*.nii',
        '**/*.nii.gz',
        '**/*.nii'
    ]
    
    for pattern in patterns:
        files = sorted(dataset_dir.glob(pattern))
        if files:
            return files[0]
    
    return None


def generate_preview_image(image_path: Path, num_cols: int = 5):
    """
    Generate a preview image of the first scan.
    
    Args:
        image_path: Path to NIfTI file
        num_cols: Number of columns for the grid
        
    Returns:
        Base64-encoded PNG image string
    """
    try:
        # Create the plot
        fig = create_overlay_grid_3xN(
            underlay_data=str(image_path),
            overlay_data=None,
            num_cols=num_cols
        )
        
        # Convert to base64
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        
        return img_base64
    except Exception as e:
        print(f"Warning: Could not generate preview image: {e}")
        return None


def create_server(html_content: str, port: int = 8000):
    """
    Create a simple HTTP server to serve the HTML.
    
    Args:
        html_content: HTML content to serve
        port: Port number
        
    Returns:
        Server instance
    """
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/' or self.path == '/config_generator.html':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(html_content.encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()
    
    server = socketserver.TCPServer(("", port), Handler)
    return server


def main():
    parser = argparse.ArgumentParser(
        description='Launch macacaMRIprep configuration generator with dataset preview'
    )
    parser.add_argument(
        'dataset_dir',
        type=str,
        help='Path to BIDS dataset directory'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port number for the web server (default: 8000)'
    )
    parser.add_argument(
        '--no-browser',
        action='store_true',
        help='Do not open browser automatically'
    )
    
    args = parser.parse_args()
    
    dataset_dir = Path(args.dataset_dir).resolve()
    
    # Find first scan
    print(f"Searching for first scan in: {dataset_dir}")
    first_scan = find_first_scan(dataset_dir)
    
    if first_scan is None:
        print("Warning: No NIfTI files found in dataset. Preview image will not be available.")
        preview_base64 = None
    else:
        print(f"Found first scan: {first_scan}")
        print("Generating preview image...")
        preview_base64 = generate_preview_image(first_scan, num_cols=5)
        if preview_base64:
            print("Preview image generated successfully")
        else:
            print("Warning: Could not generate preview image")
    
    # Load the HTML template
    config_dir = Path(__file__).parent
    html_path = config_dir / 'config_generator.html'
    
    if not html_path.exists():
        print(f"Error: HTML template not found: {html_path}")
        sys.exit(1)
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Inject dataset_dir and preview image into HTML
    # Add preview image if available
    if preview_base64:
        preview_html = f'''
        <div id="preview-section" style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; background: #f9f9f9;">
            <h3>Dataset Preview (First Scan)</h3>
            <p>Preview of the first scan found in the dataset to help determine orientation settings:</p>
            <img src="data:image/png;base64,{preview_base64}" alt="Dataset Preview" style="max-width: 100%; height: auto; border: 1px solid #ccc;">
        </div>
        '''
        # Insert at the placeholder or before orientation_mismatch_correction section
        if '<!-- PREVIEW_PLACEHOLDER -->' in html_content:
            html_content = html_content.replace(
                '<!-- PREVIEW_PLACEHOLDER -->',
                preview_html
            )
        else:
            # Fallback: insert before orientation_mismatch_correction section
            insert_marker = '<h2>orientation_mismatch_correction</h2>'
            if insert_marker in html_content:
                html_content = html_content.replace(
                    insert_marker,
                    preview_html + '\n        ' + insert_marker
                )
            else:
                # If marker not found, append at the end before closing body
                html_content = html_content.replace(
                    '</body>',
                    preview_html + '\n    </body>'
                )
    
    # Note: dataset_dir is no longer in the form, but we can still use it for preview
    
    # Start server
    print(f"Starting web server on port {args.port}...")
    try:
        server = create_server(html_content, args.port)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        url = f"http://localhost:{args.port}/"
        print(f"Configuration generator available at: {url}")
        
        if not args.no_browser:
            print("Opening browser...")
            time.sleep(1)  # Give server time to start
            webbrowser.open(url)
        
        print("\nPress Ctrl+C to stop the server...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down server...")
            server.shutdown()
            
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"Error: Port {args.port} is already in use. Try a different port with --port")
        else:
            print(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

