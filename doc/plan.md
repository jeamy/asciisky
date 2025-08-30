# ASCII Sky - Development Plan

## Features Implemented

1. **ASCII Horizon Line**
   - ✅ Created a dynamic horizon line using ASCII characters
   - ✅ Added cardinal directions (N, O, S, W)
   - ✅ Adjusted line dynamically based on object position

2. **Celestial Object Positioning**
   - ✅ Calculated correct position for celestial objects in the ASCII sky
   - ✅ Showed object position relative to horizon
   - ✅ Handled objects below the horizon
   - ✅ Added special symbols for objects below the horizon

3. **Interactive Menu**
   - ✅ Created an object selection menu for celestial objects
   - ✅ Included Sun, Moon, and planets
   - ✅ Added object information on selection

4. **Object Information Dialog**
   - ✅ Displayed detailed information when an object is selected
   - ✅ Showed current position, distance, and other relevant data
   - ✅ Added rise, set, and transit times for all celestial objects
   - ✅ Included closable dialog with X button

## Recent Improvements

### Backend (Python/FastAPI)
- ✅ Added API endpoints for celestial objects
- ✅ Implemented constants for API endpoints and astronomical values
- ✅ Fixed serialization issues with celestial body data
- ✅ Improved error handling for missing celestial bodies
- ✅ Added calculation of rise, set, and transit times for all celestial objects
- ✅ Modified visibility logic to always show objects below the horizon
- ✅ Implemented bright asteroids pipeline with IAU H–G magnitude model
  - Use `mpc.mpcorb_orbit()` and observe `sun + orbit` from an Earth `Topos`
  - Compute heliocentric distance r, observer distance Δ, phase angle α
  - Apply H–G magnitude: `V = H + 5 log10(rΔ) − 2.5 log10((1−G)Φ1 + GΦ2)`
  - Two-stage filtering: `MAX_ABSOLUTE_MAGNITUDE (H)` and `MAX_APPARENT_MAGNITUDE (V)`
  - Rise/Set/Transit via `almanac` with `sun + orbit` and `Topos`

### Frontend (JavaScript)
- ✅ Centralized constants in constants.js
- ✅ Fixed recursion bug in skyRenderer.js
- ✅ Improved rendering performance
- ✅ Added proper symbol mapping for celestial objects
- ✅ Enhanced object dialog with rise, set, and transit times
- ✅ Improved positioning of objects below the horizon
- ✅ Implemented internationalization (i18n) with German as default language
- ✅ Improved multi-object dialog with minimalist design and better spacing
- ✅ Moved dialog CSS to external file for better maintainability
- ✅ Added loading indicator while fetching bright asteroids
- ✅ Simplified asteroid display names (strip numeric designations like "(4) Vesta")

### Code Organization
- ✅ Moved all constants to constants.js
- ✅ Created separate modules for different functionality
- ✅ Added documentation and comments

## Ongoing Tasks

### Backend
- [ ] Add more celestial bodies (asteroids, comets)
- [ ] Implement time-based simulation controls

### Frontend
- [ ] Add responsive design for different screen sizes
- [ ] Implement animation for object movement
- [ ] Add search functionality for celestial objects

### UI/UX
- [ ] Improve ASCII art for different objects
- [ ] Add help/instructions panel
- [ ] Create user preferences for display options

## Technical Considerations
- Using Skyfield for accurate astronomical calculations
- Docker for consistent deployment environment
- Centralized constants for better maintainability
- Optimized rendering to prevent recursion issues
- H–G magnitude implementation and asteroid selection documented in `doc/asteroids.md`
