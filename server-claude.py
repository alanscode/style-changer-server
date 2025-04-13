import os
import asyncio
import subprocess
import sys
import datetime
import pathlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from anthropic import Anthropic
from dotenv import load_dotenv
import concurrent.futures
from bs4 import BeautifulSoup, Comment  # Added for HTML cleaning
import re  # For regex pattern matching

# Load environment variables from .env file
load_dotenv()

# Configure the Anthropic API client
try:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise ValueError("ANTHROPIC_API_KEY not found or not set in .env file.")
    client = Anthropic(api_key=api_key)
except ValueError as e:
    print(f"Error configuring Anthropic API: {e}")
    # Optionally, exit or handle the error appropriately if the key is essential
    # For now, we'll let the server start but API calls will fail later.
    client = None

# Define the request body model using Pydantic
# Added html_structure and current_styles
class RestyleRequest(BaseModel):
    prompt: str
    html_structure: str

# Create the FastAPI app instance
app = FastAPI()

# --- CORS Middleware Configuration ---
# Allow requests from the extension's content script
# WARNING: Allowing all origins ("*") is convenient for development but insecure for production.
# Restrict origins in a real deployment.
origins = [
    "*", # Allows all origins
    # Example for specific origins:
    # "https://www.reddit.com",
    # "https://news.ycombinator.com",
    # "chrome-extension://<your-extension-id>" # Replace with your actual extension ID
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allows cookies if needed (not strictly necessary here)
    allow_methods=["*"],    # Allows all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],    # Allows all headers
)
# --- End CORS Configuration ---

def clean_html_for_llm(html_content: str) -> str:
    """
    Removes elements and attributes from HTML that are unlikely to be relevant
    for high-level CSS styling generation, reducing token count.
    """
    if not html_content:
        return ""

    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Use lxml parser

        # 1. Remove <script>, <style>, <meta>, <link> tags
        for tag in soup.find_all(['script', 'style', 'meta', 'link']):
            # Keep CSS links if needed, but for overrides, we're removing all
            tag.decompose()  # Removes the tag and its content

        # 2. Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # 3. Clean SVG content (keep SVG tag but remove its children)
        for svg in soup.find_all('svg'):
            svg.clear()  # Removes children like <path>, <g>

        # 4. Remove hidden elements
        # 4.1 Elements with hidden attribute
        for hidden_elem in soup.find_all(attrs={"hidden": True}):
            hidden_elem.decompose()
            
        # 4.2 Known non-visible elements (spinners, tooltips, skeleton loaders)
        non_visible_patterns = [
            'spinner', 'tooltip', 'skeleton', 'loading', 'hidden', 
            'invisible', 'offscreen', 'visually-hidden'
        ]
        for pattern in non_visible_patterns:
            # Find elements with class or id containing these patterns
            for elem in soup.find_all(class_=re.compile(pattern, re.IGNORECASE)):
                elem.decompose()
            for elem in soup.find_all(id=re.compile(pattern, re.IGNORECASE)):
                elem.decompose()
                
        # 4.3 YouTube-specific non-visible elements
        youtube_non_visible = [
            'tp-yt-paper-spinner-lite', 'tp-yt-paper-tooltip', 
            'ytd-popup-container', 'ytd-miniplayer'
        ]
        for elem_type in youtube_non_visible:
            for elem in soup.find_all(elem_type):
                elem.decompose()

        # 5. Remove tracking/metadata attributes and accessibility attributes
        attributes_to_remove = [
            # Tracking/metadata attributes
            'itemprop', 'itemscope', 'itemtype', 'trackingParams', 
            'nonce', 'jslog', 'ved', 'ftl-eligible',
            'notify-on-loaded', 'notify-on-unloaded',
            # Accessibility attributes (careful with these)
            'role', 'aria-label', 'aria-labelledby', 'aria-hidden',
            'aria-expanded', 'aria-haspopup', 'aria-controls',
            'aria-checked', 'aria-selected', 'aria-current',
            'aria-disabled', 'aria-describedby'
        ]
        
        # 6. Handle data-* attributes and sanitized attributes separately
        for tag in soup.find_all(True):  # Find all tags
            attrs_copy = dict(tag.attrs)  # Create a copy to avoid modification during iteration
            for attr in attrs_copy:
                # Remove data-* attributes
                if attr.startswith('data-') or attr in attributes_to_remove:
                    del tag[attr]
                
                # Replace sanitized href/src attributes with minimal placeholders
                if attr in ['href', 'src'] and attrs_copy[attr] and ('[sanitized' in attrs_copy[attr] or 
                                                                     'javascript:' in attrs_copy[attr]):
                    tag[attr] = '#'  # Replace with minimal placeholder
        
        # 7. Attempt to remove redundant div wrappers (with caution)
        # This is a simplified approach - only removes completely empty divs or divs with only whitespace
        for div in soup.find_all('div'):
            # Check if div has no attributes and only contains whitespace or nothing
            if (not div.attrs and (not div.string or not div.string.strip()) and 
                not div.find_all(True)):  # No child elements
                div.decompose()
        
        # Return the cleaned HTML as a string
        return str(soup)

    except Exception as e:
        print(f"Error cleaning HTML: {e}")
        return html_content  # Return original on error

def save_html_structure(html_structure, prompt):
    """Save the HTML structure to a file in the requests folder if enabled."""
    # Check if HTML logging is enabled
    enable_html_logging = os.getenv("ENABLE_HTML_LOGGING", "false").lower() == "true"
    
    if not enable_html_logging:
        print("HTML logging is disabled. Skipping HTML save.")
        return "HTML logging disabled"
    
    # Create requests directory if it doesn't exist
    requests_dir = pathlib.Path("requests")
    requests_dir.mkdir(exist_ok=True)
    
    # Create a filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Create a safe filename from the prompt (first 30 chars, alphanumeric only)
    safe_prompt = ''.join(c for c in prompt if c.isalnum() or c in ' _-')[:30].strip().replace(' ', '_')
    filename = f"{timestamp}_{safe_prompt}.html"
    
    # Save the HTML structure to the file
    file_path = requests_dir / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_structure)
    
    print(f"Saved HTML structure to {file_path}")
    return str(file_path)

def save_css(css_content, prompt):
    """Save the generated CSS to a file in the css folder if enabled."""
    # Check if CSS logging is enabled
    enable_css_logging = os.getenv("ENABLE_CSS_LOGGING", "false").lower() == "true"
    
    if not enable_css_logging:
        print("CSS logging is disabled. Skipping CSS save.")
        return "CSS logging disabled"
    
    # Create css directory if it doesn't exist
    css_dir = pathlib.Path("css")
    css_dir.mkdir(exist_ok=True)
    
    # Create a filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Create a safe filename from the prompt (first 30 chars, alphanumeric only)
    safe_prompt = ''.join(c for c in prompt if c.isalnum() or c in ' _-')[:30].strip().replace(' ', '_')
    filename = f"{timestamp}_{safe_prompt}.css"
    
    # Save the CSS to the file
    file_path = css_dir / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(css_content)
    
    print(f"Saved CSS to {file_path}")
    return str(file_path)

# Define the POST endpoint /restyle
@app.post("/restyle")
async def restyle_endpoint(request: RestyleRequest):
    """
    Receives an art direction prompt, current HTML structure, and current CSS,
    uses Anthropic's Claude to generate CSS style overrides, and returns the generated CSS.
    """
    if not client:
        raise HTTPException(status_code=500, detail="Anthropic client not initialized. Check API key and configuration.")

    print(f"Received prompt: {request.prompt}")  # Print the prompt upon receiving the request
    
    # Check if logging is enabled
    enable_html_logging = os.getenv("ENABLE_HTML_LOGGING", "false").lower() == "true"
    enable_css_logging = os.getenv("ENABLE_CSS_LOGGING", "false").lower() == "true"
    
    # Clean the HTML structure to reduce token count
    cleaned_html = clean_html_for_llm(request.html_structure)
    
    # Save only the cleaned HTML if logging is enabled
    cleaned_html_path = save_html_structure(cleaned_html, request.prompt) if enable_html_logging else "HTML logging disabled"
    
    # Calculate token reduction (approximate)
    original_tokens = len(request.html_structure) / 4  # Rough estimate
    cleaned_tokens = len(cleaned_html) / 4  # Rough estimate
    token_reduction = original_tokens - cleaned_tokens
    token_reduction_percent = (token_reduction / original_tokens) * 100 if original_tokens > 0 else 0
    
    print(f"HTML cleaning reduced tokens by approximately {token_reduction:.0f} tokens ({token_reduction_percent:.1f}%)")
    
    # Updated system prompt to include HTML and CSS context
    system_prompt = f"""You are a world-class, highly creative web designer. Your task is to generate CSS code that overrides
    the styles of a webpage to satisfy a specific art direction, based *only* on the provided HTML structure.
    
    Context:
    1.  **Art Direction:** {request.prompt}
    2.  **Current HTML Structure (simplified):**
        ```html
        {cleaned_html}
        ```
    
    Instructions:
    - Be highly creative and bold in your CSS design choices.
    - Over use small animations and transitions to make the page feel alive.
    - In addition to changing colors (background, text, links, accents), also creatively modify:
        • Border styles (width, color, style: solid, dashed, double, etc.)
        • Border radius (rounded corners, pill shapes, etc.)
        • Box shadows and text shadows for glowing effects
        • Add !important to everything to ensure it overrides existing styles.
        • Background images, colors, gradients, transparency, or patterns
        • Text shadows, text decorations (underline, line-through)
        • Font families, font weights, and font styles
        • Spacing (padding, margin, letter-spacing, line-height)
        • Button and input styles (hover, active, focus states)
        • Any other visually impactful CSS properties
        • Hover states, active states, and focus states should be included for interactive elements.
    - Use a variety of CSS features to make the theme visually distinct and interesting.
    - Ensure the CSS selectors are specific enough to target the intended elements based on the HTML structure.
    - Ensure that foreground text and background colors have opposing contrast for readability.
    - Do not include explanations or markdown formatting like ```css. Only return the raw CSS code.
    """

    try:
        # Claude API call with increased max_tokens to ensure complete CSS response
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=8192,  # Increased from 1024 to 4096 to ensure complete CSS
            messages=[
                {"role": "user", "content": system_prompt}
            ]
        )

        # Extract the generated CSS from the response
        generated_style = response.content[0].text

        # Save the CSS to a file if logging is enabled
        css_file_path = save_css(generated_style, request.prompt) if enable_css_logging else "CSS logging disabled"

        print(f"Generated CSS length: {len(generated_style)} characters")
        # Print a preview of the CSS (first 500 characters)
        print(f"CSS Preview:\n{generated_style[:500]}...")

        # Return only the generated style as requested
        return {
            "generated_style": generated_style
        }

    except Exception as e:
        print(f"Error during Claude API call: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating style: {e}")

def check_and_kill_port(port):
    """Check if the port is in use and kill the process if it is."""
    if sys.platform == 'win32':
        # Windows
        try:
            # Check if port is in use
            result = subprocess.run(
                ['powershell', '-Command',
                 f'$connections = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; '
                 f'if ($connections) {{ '
                 f'  $processes = Get-Process -Id $connections.OwningProcess; '
                 f'  Write-Host "Found processes using port {port}:"; '
                 f'  $processes | ForEach-Object {{ Write-Host "- $($_.Id): $($_.ProcessName)" }}; '
                 f'  $processes | Stop-Process -Force; '
                 f'  Write-Host "Killed processes using port {port}"; '
                 f'}} else {{ '
                 f'  Write-Host "No processes found using port {port}"; '
                 f'}}'
                ],
                capture_output=True,
                text=True
            )
            print(result.stdout)
            if result.stderr:
                print(f"Error: {result.stderr}")
        except Exception as e:
            print(f"Error checking/killing port {port}: {e}")
    else:
        # Linux/Mac
        try:
            # Find process using the port
            result = subprocess.run(
                ['lsof', '-i', f':{port}', '-t'],
                capture_output=True,
                text=True
            )
            pids = result.stdout.strip().split('\n')
            
            if pids and pids[0]:
                print(f"Found processes using port {port}: {', '.join(pids)}")
                # Kill each process
                for pid in pids:
                    if pid:
                        subprocess.run(['kill', '-9', pid])
                print(f"Killed processes using port {port}")
            else:
                print(f"No processes found using port {port}")
        except Exception as e:
            print(f"Error checking/killing port {port}: {e}")

# Basic entry point to run the server with uvicorn
if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY") == "YOUR_API_KEY_HERE":
        print("\nWARNING: ANTHROPIC_API_KEY is not set or is still the placeholder.")
        print("Please set your actual API key in the .env file for the application to work correctly.\n")
    
    # Log environment settings
    enable_html_logging = os.getenv("ENABLE_HTML_LOGGING", "false").lower() == "true"
    enable_css_logging = os.getenv("ENABLE_CSS_LOGGING", "false").lower() == "true"
    print(f"HTML Logging: {'Enabled' if enable_html_logging else 'Disabled'}")
    print(f"CSS Logging: {'Enabled' if enable_css_logging else 'Disabled'}")
    
    # Get server host and port from environment variables or use defaults
    server_host = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port = int(os.getenv("SERVER_PORT", "8000"))
    
    # Check and kill any processes using the specified port
    print(f"Checking for processes using port {server_port}...")
    check_and_kill_port(server_port)

    print(f"Starting server on {server_host}:{server_port}...")
    uvicorn.run(app, host=server_host, port=server_port)