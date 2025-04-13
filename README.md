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
  "generated_style": "/* CSS styles here */",
  "html_saved_to": "requests/20250413_123456_make_it_look_like_a_cyberpunk_i.html",
  "css_saved_to": "css/20250413_123456_make_it_look_like_a_cyberpunk_i.css",
  "token_reduction": "10000 tokens (75.0%)"
}
```

## HTML Cleaning

The server includes an advanced HTML cleaning function that significantly reduces token usage by removing elements and attributes that are not relevant for CSS styling:

### High-Impact Removals
- Removes all `<script>` tags and their content
- Removes all `<meta>` tags
- Removes `<link>` tags
- Removes any inline `<style>` blocks
- Cleans SVG content (keeps the SVG tag but removes its children)
- Removes tracking/metadata attributes (data-*, itemprop, etc.)
- Removes all HTML comments

### Medium-Impact Removals
- Removes hidden elements (with hidden attribute)
- Removes known non-visible elements (spinners, tooltips, skeleton loaders)
- Replaces sanitized attributes (href="[sanitized-href]", src="[sanitized-src]") with minimal placeholders
- Removes accessibility attributes (aria-*, role)
- Attempts to remove redundant `<div>` wrappers (empty or whitespace-only divs)

This cleaning process can reduce token usage by 50-90% depending on the page, which:
1. Reduces API costs
2. Improves response times
3. Allows for processing of larger pages that might otherwise exceed token limits

## File Storage

The server saves files for debugging and reference:

- **Cleaned HTML**: Saved in the `requests` folder with a timestamp and prompt-based filename
- **Generated CSS**: Saved in the `css` folder with a timestamp and prompt-based filename

## CSS Generation

The server uses Claude 3.7 Sonnet to generate CSS with the following features:

- Uses a high max_tokens value (4096) to ensure complete CSS responses
- Instructs the model to create highly creative and bold design choices
- Emphasizes animations, transitions, and visual effects
- Ensures proper contrast for readability
- Includes hover, active, and focus states for interactive elements

## Chrome Extension

This server is designed to work with the Style Changer Chrome extension. The extension sends the current page's HTML structure and a user-provided art direction prompt to this server, which then returns generated CSS styles to apply to the page.