#!/usr/bin/env python3
"""
CLI tool to launch the nhp_mri_prep configuration generator.

This script:
1. Optionally takes a dataset_dir argument for preview image
2. If provided, finds the first scan in the BIDS dataset and generates a preview
3. Launches the HTML config generator (with preview if dataset_dir provided)
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
    from nhp_mri_prep.quality_control.mri_plotting import create_overlay_grid_3xN
except ImportError as e:
    print(f"Error importing plotting utilities: {e}")
    sys.exit(1)

try:
    from nhp_mri_prep.config.config_io import get_default_config
except ImportError as e:
    print(f"Error importing config utilities: {e}")
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
        description='Launch nhp_mri_prep configuration generator'
    )
    parser.add_argument(
        'dataset_dir',
        type=str,
        nargs='?',
        default=None,
        help='Optional: Path to BIDS dataset directory for preview image'
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
    
    preview_base64 = None
    
    # Generate preview if dataset_dir is provided
    if args.dataset_dir:
        dataset_dir = Path(args.dataset_dir).resolve()
        
        # Find first scan
        print(f"Searching for first scan in: {dataset_dir}")
        first_scan = find_first_scan(dataset_dir)
        
        if first_scan is None:
            print("Warning: No NIfTI files found in dataset. Preview image will not be available.")
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
    
    # Load defaults from defaults.yaml and inject into HTML
    try:
        defaults = get_default_config()
        import json
        
        # Convert Python dict to JSON string (JSON is valid JavaScript)
        defaults_json = json.dumps(defaults, indent=12)  # 12 spaces to match existing indentation
        
        # Replace the hardcoded defaults object in the JavaScript
        # Find the line with "const defaults = {" and replace until the closing "};"
        lines = html_content.split('\n')
        new_lines = []
        in_defaults = False
        found_defaults = False
        
        for line in lines:
            if 'const defaults = {' in line and not found_defaults:
                # Found the start - replace with new defaults
                # Preserve the indentation from the original line
                indent = len(line) - len(line.lstrip())
                # JSON is already properly formatted, just prepend base indent to each line
                json_lines = defaults_json.split('\n')
                indented_json = '\n'.join(' ' * indent + json_line for json_line in json_lines)
                new_lines.append(' ' * indent + 'const defaults = ' + indented_json + ';')
                in_defaults = True
                found_defaults = True
                continue
            elif in_defaults:
                # Skip lines until we find the closing "};"
                if line.strip() == '};':
                    in_defaults = False
                # Skip all lines within the defaults block
                continue
            else:
                new_lines.append(line)
        
        html_content = '\n'.join(new_lines)
        
        if not found_defaults:
            print("Warning: Could not find 'const defaults = {' in HTML. Defaults not injected.")
    except Exception as e:
        print(f"Warning: Could not load defaults from defaults.yaml: {e}")
        print("HTML will use hardcoded defaults.")
    
    # Add preview image if available
    if preview_base64:
        preview_html = f'''
        <div id="preview-section" style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; background: #f9f9f9;">
            <h3>Dataset Preview (First Scan)</h3>
            <p>Preview of the first scan found in the dataset:</p>
            <img src="data:image/png;base64,{preview_base64}" alt="Dataset Preview" style="max-width: 100%; height: auto; border: 1px solid #ccc;">
        </div>
        '''
        # Insert at the placeholder or before the generate button
        if '<!-- PREVIEW_PLACEHOLDER -->' in html_content:
            html_content = html_content.replace(
                '<!-- PREVIEW_PLACEHOLDER -->',
                preview_html
            )
        else:
            # Fallback: insert before the generate button
            insert_marker = '<button type="button" onclick="generateConfig()">Generate Preprocessing Configuration File</button>'
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

