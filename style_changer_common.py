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
from dotenv import load_dotenv
import concurrent.futures
from bs4 import BeautifulSoup, Comment
import re

# Load environment variables from .env file
load_dotenv()

# Define the request body model using Pydantic
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
    "*",  # Allows all origins
    # Example for specific origins:
    # "https://www.reddit.com",
    # "https://news.ycombinator.com",
    # "chrome-extension://<your-extension-id>" # Replace with your actual extension ID
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # Allows cookies if needed (not strictly necessary here)
    allow_methods=["*"],     # Allows all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],     # Allows all headers
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

def get_env_settings():
    """Helper to get environment settings for server host, port, and logging flags."""
    enable_html_logging = os.getenv("ENABLE_HTML_LOGGING", "false").lower() == "true"
    enable_css_logging = os.getenv("ENABLE_CSS_LOGGING", "false").lower() == "true"
    server_host = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port = int(os.getenv("SERVER_PORT", "8000"))
    return server_host, server_port, enable_html_logging, enable_css_logging

def get_system_prompt(art_direction: str, cleaned_html: str) -> str:
    """
    Generate the system prompt for the LLM to generate CSS overrides.
    :param art_direction: The art direction prompt from the user.
    :param cleaned_html: The cleaned HTML structure.
    :return: The formatted system prompt string.
    """
    return (
        f"You are a creative web designer. Your task is to generate CSS code that overrides\n"
        f"the styles of a webpage to satisfy a specific art direction, based *only* on the provided HTML structure.\n"
        f"\n"
        f"Context:\n"
        f"1.  **Art Direction:** {art_direction}\n"
        f"2.  **Current HTML Structure (simplified):**\n"
        f"    ```html\n"
        f"    {cleaned_html}\n"
        f"    ```\n"
        f"\n"
        f"Instructions:\n"
        f"- Be highly creative and bold in your CSS design choices while at the same time make it a PRIORITY to IMPROVE the UI if possible.\n"
        f"- Over use small animations and transitions to make the page feel alive.\n"
        f"- In addition to changing colors (background, text, links, accents), also creatively modify:\n"
        f"    • Border styles (width, color, style: solid, dashed, double, etc.)\n"
        f"    • Border radius (rounded corners, pill shapes, etc.)\n"
        f"    • Box shadows and text shadows for glowing effects\n"
        f"    • Add !important to everything to ensure it overrides existing styles.\n"
        f"    • Background images, colors, gradients, transparency, or patterns\n"
        f"    • Text shadows, text decorations (underline, line-through)\n"
        f"    • Font families, font weights, and font styles\n"
        f"    • Spacing (padding, margin, letter-spacing, line-height)\n"
        f"    • Button and input styles (hover, active, focus states)\n"
        f"    • Any other visually impactful CSS properties\n"
        f"    • Hover states, active states, and focus states should be included for interactive elements.\n"
        f"- Use a variety of CSS features to make the theme visually distinct and interesting.\n"
        f"- Ensure the CSS selectors are specific enough to target the intended elements based on the HTML structure.\n"
        f"- Ensure that foreground text and background colors have opposing contrast for readability.\n"
        f"- Do not include explanations or markdown formatting like ```css. Only return the raw CSS code.\n"
        f"- Reject any and all javascript \n"
    )