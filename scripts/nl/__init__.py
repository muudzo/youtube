"""
Dutch brainrot channel — a separate production surface from the English
dark-history pipeline in the parent package.

Design constraint that shapes every module here: YouTube's inauthentic-content
policy demonetizes "generic, repetitive, or template-based content" reproduced
at scale. The English pipeline's fingerprint — one voice, one structure, one
thumbnail template, upload-until-quota-dry — is precisely what gets flagged.
So this package rotates every observable knob per video (variation.py), caps
cadence to a human rate (config.NL_MAX_UPLOADS_PER_DAY), demands an original
angle from the model (script_generator.py), and discloses synthetic media on
upload (produce.py).
"""
