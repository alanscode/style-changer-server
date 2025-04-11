import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure the Google Gemini API client
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise ValueError("GOOGLE_API_KEY not found or not set in .env file.")
    genai.configure(api_key=api_key)
except ValueError as e:
    print(f"Error configuring Gemini API: {e}")
    # Optionally, exit or handle the error appropriately if the key is essential
    # For now, we'll let the server start but API calls will fail later.

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

# Initialize the Generative Model
try:
    model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
except Exception as e:
    print(f"Error initializing Generative Model: {e}")
    model = None # Set model to None if initialization fails

# Define the POST endpoint /restyle
@app.post("/restyle")
async def restyle_endpoint(request: RestyleRequest):
    """
    Receives an art direction prompt, current HTML structure, and current CSS,
    uses Google Gemini to generate CSS style overrides, and returns the generated CSS.
    """
    if not model:
        raise HTTPException(status_code=500, detail="Generative model not initialized. Check API key and configuration.")

    # Updated system prompt to include HTML and CSS context
    system_prompt = f"""You are a world-class web creative designer. Your task is to generate CSS code that overrides the styles of a webpage to satisfy a specific art direction, based *only* on the provided HTML structure.

Context:
1.  **Art Direction:** {request.prompt}
2.  **Current HTML Structure (simplified):**
    ```html
    {request.html_structure}
    ```

Based *only* on the art direction and the provided HTML structure, generate the necessary CSS override code.
Ensure the CSS selectors are specific enough to target the intended elements based on the HTML structure.
Do not include explanations or markdown formatting like ```css. Only return the raw CSS code.
"""

    try:
        # Generate content using the model
        response = model.generate_content(system_prompt)

        # Basic error handling for the response
        if not response.candidates or not response.candidates[0].content.parts:
             raise HTTPException(status_code=500, detail="Failed to generate style from Gemini API.")

        generated_style = response.text

        print(f"Received prompt: {request.prompt}")
        # Avoid printing potentially large HTML/CSS in logs by default
        # print(f"HTML Structure: {request.html_structure[:200]}...") # Example: Log snippet
        # print(f"Current Styles: ...") # Removed field
        print(f"Generated CSS:\n{generated_style}")

        # Return the generated style along with the original request data for context
        return {
            "received_prompt": request.prompt,
            "generated_style": generated_style
        }

    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating style: {e}")

# Basic entry point to run the server with uvicorn
if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "YOUR_API_KEY_HERE":
        print("\nWARNING: GOOGLE_API_KEY is not set or is still the placeholder.")
        print("Please set your actual API key in the .env file for the application to work correctly.\n")

    print("Starting server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)