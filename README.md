# Style Changer Server (Claude)

This is a FastAPI server that uses Anthropic's Claude API to generate CSS styles based on art direction prompts and HTML structure.

## Setup

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   
   Or with uv (recommended):
   ```
   uv pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory with your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   ```
   
   You can get an API key from [Anthropic's website](https://console.anthropic.com/).

## Running the Server

Start the server with:

```
python server-claude.py
```

The server will run on `http://localhost:8000`.

## API Endpoints

### POST /restyle

Generates CSS styles based on an art direction prompt and HTML structure.

**Request Body:**

```json
{
  "prompt": "Make it look like a cyberpunk interface",
  "html_structure": "<div class='container'>...</div>"
}
```

**Response:**

```json
{
  "received_prompt": "Make it look like a cyberpunk interface",
  "generated_style": "/* CSS styles here */"
}
```

## Chrome Extension

This server is designed to work with the Style Changer Chrome extension. The extension sends the current page's HTML structure and a user-provided art direction prompt to this server, which then returns generated CSS styles to apply to the page.