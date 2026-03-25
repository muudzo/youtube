#!/bin/zsh
# Remove stock footage older than 7 days to save disk space
find /Users/tatendanyemudzo/youtube/assets/stock_footage -name "*.mp4" -mtime +7 -delete 2>/dev/null
echo "Cleanup done: $(date)"
