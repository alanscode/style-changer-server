import os
import asyncio
import subprocess
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from anthropic import Anthropic
from dotenv import load_dotenv
import concurrent.futures

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

# Define the POST endpoint /restyle
@app.post("/restyle")
async def restyle_endpoint(request: RestyleRequest):
    """
    Receives an art direction prompt, current HTML structure, and current CSS,
    uses Anthropic's Claude to generate CSS style overrides, and returns the generated CSS.
    """
    if not client:
        raise HTTPException(status_code=500, detail="Anthropic client not initialized. Check API key and configuration.")

    print(f"Received prompt: {request.prompt}") # Print the prompt upon receiving the request
    # Updated system prompt to include HTML and CSS context
    system_prompt = f"""You are a world-class, highly creative web designer. Your task is to generate CSS code that overrides
    the styles of a webpage to satisfy a specific art direction, based *only* on the provided HTML structure.
    
    Context:
    1.  **Art Direction:** {request.prompt}
    2.  **Current HTML Structure (simplified):**
        ```html
        {request.html_structure}
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
        # Claude API call
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": system_prompt}
            ]
        )

        # Extract the generated CSS from the response
        generated_style = response.content[0].text

        print(f"Received prompt: {request.prompt}")
        # Avoid printing potentially large HTML/CSS in logs by default
        # print(f"HTML Structure: {request.html_structure[:200]}...") # Example: Log snippet
        print(f"Generated CSS:\n{generated_style}")

        # Return the generated style along with the original request data for context
        return {
            "received_prompt": request.prompt,
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
    
    # Check and kill any processes using port 8000
    print("Checking for processes using port 8000...")
    check_and_kill_port(8000)

    print("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)