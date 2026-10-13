# TUTAR X Logo Visual Verification Checklist

Use this checklist after starting the development server (`npm run dev`) to verify the logo integration visually.

---

## Pre-Verification Setup

1. Start the frontend development server:
   ```bash
   cd frontend
   npm run dev
   ```

2. Open browser to `http://localhost:5173` (or the displayed port)

---

## Visual Verification Checklist

### ✅ Sidebar Logo (Desktop)

**Test: Full Sidebar**
- [ ] Logo displays in the sidebar brand section (top)
- [ ] Logo is clear and readable
- [ ] Logo maintains aspect ratio (not stretched/squished)
- [ ] Logo has the following elements visible:
  - [ ] Golden "X" in center
  - [ ] Green upward arrow
  - [ ] Green bar chart elements
  - [ ] White circular frame
  - [ ] Soccer ball icon (top-right)
  - [ ] White dashed outer ring
- [ ] Tagline "Maçın geleceğini veriden oku." displays below logo
- [ ] Hover effect works (logo brightens slightly)

**Test: Collapsed Sidebar**
- [ ] Click the collapse button (← arrow at bottom of sidebar)
- [ ] Logo scales down but remains visible
- [ ] Logo maintains aspect ratio when smaller
- [ ] Tagline disappears in collapsed mode
- [ ] Logo still clearly shows key brand elements

**Test: Expand Sidebar Again**
- [ ] Click expand button (→ arrow)
- [ ] Logo smoothly transitions back to full size
- [ ] Tagline reappears
- [ ] Animation is smooth (no flicker or jump)

---

### ✅ Browser Tab (Favicon)

- [ ] Look at browser tab for the application
- [ ] TUTAR X logo appears as the favicon
- [ ] Favicon is recognizable at small size
- [ ] Favicon persists when switching tabs

**Multi-Tab Test:**
- [ ] Open application in multiple tabs
- [ ] Each tab shows the logo favicon
- [ ] Favicon helps identify TUTAR X tabs among other tabs

---

### ✅ Mobile Responsive Behavior

**Test: Mobile Simulation (Desktop Browser)**
1. Open browser DevTools (F12)
2. Toggle device toolbar (Ctrl+Shift+M or Cmd+Shift+M)
3. Select a mobile device (e.g., iPhone 12, Galaxy S21)

**Sidebar Closed (Default Mobile)**
- [ ] Sidebar is hidden by default
- [ ] Header shows menu button (hamburger icon) on left

**Sidebar Open**
- [ ] Click hamburger menu button
- [ ] Sidebar slides in from left
- [ ] Logo displays at full size
- [ ] Logo is clearly visible on mobile screen
- [ ] Tagline displays on mobile
- [ ] Logo doesn't overflow or get cut off

**Navigation Test**
- [ ] Click any navigation link
- [ ] Sidebar closes automatically
- [ ] Can reopen sidebar and logo still displays correctly

---

### ✅ Dashboard Page

Navigate to Dashboard (default home page):
- [ ] Page title shows "TUTAR X PICKS" in gradient text
- [ ] Subtitle shows "Bugünün yapay zeka destekli maç seçimleri"
- [ ] Text branding is consistent with logo colors/theme
- [ ] Logo in sidebar provides visual reinforcement of brand

---

### ✅ Page Title

- [ ] Browser window/tab title reads: "TUTAR X — Maçın geleceğini veriden oku."
- [ ] Title is properly formatted with em dash
- [ ] Title remains consistent across all pages

---

### ✅ Visual Theme Consistency

**Color Harmony Check:**
- [ ] Logo's dark background matches app's navy/black theme
- [ ] Logo's gold/yellow "X" complements accent colors
- [ ] Logo's green elements don't clash with cyan/purple accents
- [ ] Logo's white elements match text/border colors
- [ ] Overall brand feels cohesive

**Contrast Check:**
- [ ] Logo is clearly visible against sidebar background
- [ ] All logo elements have sufficient contrast
- [ ] Logo is readable in both light and dark conditions (adjust monitor brightness to test)

---

### ✅ Cross-Browser Testing (Optional)

Test in multiple browsers if available:

**Chrome/Edge**
- [ ] Logo displays correctly
- [ ] Favicon shows in tab
- [ ] Hover effects work
- [ ] Transitions are smooth

**Firefox**
- [ ] Logo displays correctly
- [ ] Favicon shows in tab
- [ ] Hover effects work
- [ ] Transitions are smooth

**Safari (macOS/iOS)**
- [ ] Logo displays correctly
- [ ] Favicon shows in tab
- [ ] Hover effects work
- [ ] Transitions are smooth

---

### ✅ Performance Check

- [ ] Logo loads quickly (no visible delay)
- [ ] Sidebar transitions are smooth (no lag)
- [ ] No console errors related to logo
- [ ] No broken image icons
- [ ] Network tab shows logo loads successfully (200 status)

---

## Common Issues and Solutions

### Issue: Logo not displaying
- Check browser console for 404 errors
- Verify `tutarx.jpg` exists in `frontend/public/` directory
- Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)

### Issue: Logo is stretched or distorted
- Verify CSS uses `object-fit: contain`
- Check that container has proper width/height constraints
- Inspect element in DevTools to verify styles are applied

### Issue: Favicon not updating
- Clear browser cache
- Hard refresh (Ctrl+Shift+R)
- Close and reopen browser tab
- Check that `index.html` has correct favicon path

### Issue: Logo too large on mobile
- Check viewport meta tag is present
- Verify responsive CSS media queries are working
- Test in actual mobile device (not just DevTools simulation)

---

## Sign-Off

**Visual Verification Completed By:** _______________
**Date:** _______________
**Browser(s) Tested:** _______________
**Mobile Device(s) Tested:** _______________

**Overall Assessment:**
- [ ] ✅ All visual checks passed - Ready for production
- [ ] ⚠️ Minor issues found (list below) - Needs fixes
- [ ] ❌ Major issues found (list below) - Needs significant work

**Issues Found (if any):**
_______________________________________________
_______________________________________________
_______________________________________________

**Additional Notes:**
_______________________________________________
_______________________________________________
_______________________________________________

---

_Checklist version: 1.0_
_Last updated: 2026-10-07_
