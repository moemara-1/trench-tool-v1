# FrontrunPro Extension Setup

This folder should contain the FrontrunPro Chrome extension for smart follower detection.

## Setup Instructions

1. **Install FrontrunPro from Chrome Web Store:**
   - Go to: https://chromewebstore.google.com/detail/frontrunpro
   - Click "Add to Chrome"

2. **Get the extension files:**
   
   **Option A: From Chrome (easiest)**
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode" (top right)
   - Find FrontrunPro and note its Extension ID
   - Navigate to: `C:\Users\<YourUser>\AppData\Local\Google\Chrome\User Data\Default\Extensions\<EXTENSION_ID>\<VERSION>/`
   - Copy all files from that folder to this `frontrunpro/` folder

   **Option B: From GitHub (open source)**
   - Clone: https://github.com/frontrunpro/extension
   - Copy the build files to this folder

3. **Required files in this folder:**
   ```
   frontrunpro/
   ├── manifest.json
   ├── background.js
   ├── content.js
   ├── popup.html
   └── ... (other extension files)
   ```

4. **Restart the bot** - it will automatically load the extension

## How it works

When the extension is loaded:
- The scraper opens Twitter profiles in a browser with FrontrunPro
- FrontrunPro injects smart follower indicators into the page
- The scraper extracts this data for scoring

Without the extension:
- Smart followers are estimated based on crypto keywords in tweets
- Results are less accurate but still functional
