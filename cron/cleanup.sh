#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"
# Weekly cleanup — delete stock footage older than 7 days
find /Users/tatendanyemudzo/youtube/assets/stock_footage -name "*.mp4" -mtime +7 -delete 2>/dev/null
