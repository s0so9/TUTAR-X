# TUTAR X Logo Integration Notes

## Status
Awaiting official TUTAR X logo files from user.

## Required Files
- `/public/tutar-x-logo.png` or `/public/tutar-x-logo.svg` - Main logo for sidebar/header
- `/public/tutar-x-favicon.svg` or `/public/tutar-x-favicon.png` - Favicon for browser tab
- Optional: `/public/tutar-x-icon-192.png`, `/public/tutar-x-icon-512.png` for PWA (if implementing PWA later)

## Current Placeholder References
- **Frontend HTML:** `frontend/index.html` line 5 references `/tutar-x-favicon.svg`
- **Sidebar Component:** `frontend/src/components/layout/Sidebar.tsx` line 96 references `/tutar-x-logo.png`

## Integration Steps (when logo provided)
1. User provides logo files
2. Place files in `frontend/public/` directory with names:
   - `tutar-x-logo.png` (or `.svg`)
   - `tutar-x-favicon.svg` (or `.png`)
3. No code changes needed - references already point to these filenames
4. Rebuild frontend: `cd frontend && npm run build`
5. Verify logo displays correctly in sidebar and favicon appears in browser tab

## Logo Guidelines
- Logo should work on dark backgrounds (sidebar is dark navy/black)
- Favicon should be recognizable at 16x16px and 32x32px
- Recommended formats: SVG for logo (scalable), PNG for favicon
- Logo colors: white/gold/neon-green elements will stand out on dark background

## Temporary Placeholder
Until the official logo is provided, a simple text-based placeholder can be used.
The sidebar will attempt to load `/tutar-x-logo.png` (which may show a broken image until provided).
The favicon will attempt to load `/tutar-x-favicon.svg` (browser will use default if not found).
