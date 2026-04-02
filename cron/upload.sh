#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"
# Upload best videos — runs Mon/Wed/Fri at 2:42 PM CAT
cd /Users/tatendanyemudzo/youtube
source .env 2>/dev/null
export GROQ_API_KEY PEXELS_API_KEY GEMINI_API_KEY
/usr/bin/python3 autopilot.py --videos 2 >> /tmp/youtube_upload.log 2>&1
