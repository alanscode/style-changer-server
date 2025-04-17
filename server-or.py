from style_changer_common import (
    app,
    RestyleRequest,
    clean_html_for_llm,
    save_html_structure,
    save_css,
    check_and_kill_port,
    get_env_settings,
    get_system_prompt,
)
import os
import uvicorn
import socket
import httpx
from fastapi import HTTPException

# Configure the OpenRouter API key
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
if not openrouter_api_key or openrouter_api_key == "YOUR_API_KEY_HERE":
    print("WARNING: OPENROUTER_API_KEY not found or not set in .env file. API calls will fail.")

# Define the POST endpoint /restyle

@app.post("/restyle")
async def restyle_endpoint(request: RestyleRequest):
    """
    Receives an art direction prompt, current HTML structure, and current CSS,
    uses OpenRouter (ChatGPT 4.1) to generate CSS style overrides, and returns the generated CSS.
    """
    if not openrouter_api_key or openrouter_api_key == "YOUR_API_KEY_HERE":
        raise HTTPException(status_code=500, detail="OpenRouter API key not initialized. Check OPENROUTER_API_KEY in .env.")

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
    system_prompt = get_system_prompt(request.prompt, cleaned_html)

    try:
        # OpenRouter API call with increased max_tokens to ensure complete CSS response
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {
                "Authorization": f"Bearer {openrouter_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                # "model": "anthropic/claude-3.7-sonnet",
                "model": "openai/gpt-4.1-mini",
                "max_tokens": 8192,
                "messages": [
                    {"role": "user", "content": system_prompt}
                ]
            }
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload
            )
            if response.status_code != 200:
                print(f"OpenRouter API error: {response.status_code} {response.text}")
                raise HTTPException(status_code=500, detail=f"OpenRouter API error: {response.status_code} {response.text}")

            data = response.json()
            # Extract the generated CSS from the response
            generated_style = data["choices"][0]["message"]["content"]

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
        print(f"Error during OpenRouter API call: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating style: {e}")

# Basic entry point to run the server with uvicorn
if __name__ == "__main__":
    if not openrouter_api_key or openrouter_api_key == "YOUR_API_KEY_HERE":
        print("\nWARNING: OPENROUTER_API_KEY is not set or is still the placeholder.")
        print("Please set your actual OpenRouter API key in the .env file for the application to work correctly.\n")
    
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