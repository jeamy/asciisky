/**
 * Zodiac constellation renderer for ASCII Sky
 * Handles fetching and rendering of zodiac constellations
 */

import { API_ENDPOINTS, CONFIG, ASCII_ART } from './constants.js';

export class ZodiacRenderer {
    constructor(skyRenderer) {
        this.skyRenderer = skyRenderer;
        this.constellations = [];
        this.visible = true;
        this.lastFetchTime = null;
        this.fetchIntervalMs = 5 * 60 * 1000; // 5 minutes
    }

    /**
     * Fetch zodiac constellation data from the API
     * @param {Object} location - Location object with lat, lon, and elevation
     * @returns {Promise} - Promise that resolves when data is fetched
     */
    async fetchZodiacData(location) {
        try {
            // Since the ZODIAC endpoint has been removed from API_ENDPOINTS,
            // this method will do nothing but log a message
            console.log('Zodiac functionality is not implemented in this version');
            
            // Set empty constellations array to prevent rendering errors
            this.constellations = [];
            this.lastFetchTime = Date.now();
            
            // Return early without attempting to fetch
            return;
        } catch (error) {
            console.error('Error in zodiac data handling:', error);
        }
    }

    /**
     * Render zodiac constellations on the sky
     * @param {Array} skyGrid - 2D array representing the sky
     * @param {Function} getGridPosition - Function to convert alt/az to grid position
     */
    render(skyGrid, getGridPosition) {
        if (!this.visible || !this.constellations || this.constellations.length === 0) {
            return;
        }

        // Render each constellation
        for (const constellation of this.constellations) {
            this.renderConstellation(constellation, skyGrid, getGridPosition);
        }
    }

    /**
     * Render a single constellation
     * @param {Object} constellation - Constellation data
     * @param {Array} skyGrid - 2D array representing the sky
     * @param {Function} getGridPosition - Function to convert alt/az to grid position
     */
    renderConstellation(constellation, skyGrid, getGridPosition) {
        // First render the stars
        const starPositions = [];
        
        for (const star of constellation.stars) {
            if (!star.visible) continue;
            
            // Get grid position for this star
            const pos = getGridPosition(star.altitude, star.azimuth);
            if (!pos) continue;
            
            // Store position for line rendering
            starPositions.push({
                hip_id: star.hip_id,
                x: pos.x,
                y: pos.y
            });
            
            // Choose symbol based on magnitude
            let symbol = '.';
            if (star.magnitude < 1.5) symbol = '*';
            if (star.magnitude < 0.5) symbol = '★';
            
            // Place star in grid if position is valid
            if (pos.y >= 0 && pos.y < skyGrid.length && 
                pos.x >= 0 && pos.x < skyGrid[0].length) {
                skyGrid[pos.y][pos.x] = symbol;
            }
        }
        
        // Then render the lines connecting stars
        for (const [star1Id, star2Id] of constellation.lines) {
            const star1Pos = starPositions.find(s => s.hip_id === star1Id);
            const star2Pos = starPositions.find(s => s.hip_id === star2Id);
            
            if (star1Pos && star2Pos) {
                this.drawLine(star1Pos, star2Pos, skyGrid);
            }
        }
    }

    /**
     * Draw a line between two points using Bresenham's algorithm
     * @param {Object} p1 - First point {x, y}
     * @param {Object} p2 - Second point {x, y}
     * @param {Array} skyGrid - 2D array representing the sky
     */
    drawLine(p1, p2, skyGrid) {
        const dx = Math.abs(p2.x - p1.x);
        const dy = Math.abs(p2.y - p1.y);
        const sx = p1.x < p2.x ? 1 : -1;
        const sy = p1.y < p2.y ? 1 : -1;
        let err = dx - dy;
        
        let x = p1.x;
        let y = p1.y;
        
        const height = skyGrid.length;
        const width = skyGrid[0].length;
        
        while (true) {
            // Check if point is within grid bounds
            if (y >= 0 && y < height && x >= 0 && x < width) {
                // Don't overwrite stars, only empty space or sky dots
                if (skyGrid[y][x] === ' ' || skyGrid[y][x] === '.') {
                    skyGrid[y][x] = '·'; // Thin dot for constellation lines
                }
            }
            
            if (x === p2.x && y === p2.y) break;
            
            const e2 = 2 * err;
            if (e2 > -dy) {
                err -= dy;
                x += sx;
            }
            if (e2 < dx) {
                err += dx;
                y += sy;
            }
        }
    }

    /**
     * Toggle visibility of zodiac constellations
     * @returns {boolean} - New visibility state
     */
    toggleVisibility() {
        this.visible = !this.visible;
        return this.visible;
    }

    /**
     * Set visibility of zodiac constellations
     * @param {boolean} visible - Visibility state
     */
    setVisibility(visible) {
        this.visible = visible;
    }

    /**
     * Check if a point is near any constellation star
     * @param {number} x - X coordinate
     * @param {number} y - Y coordinate
     * @param {Function} getGridPosition - Function to convert alt/az to grid position
     * @returns {Object|null} - Star data if found, null otherwise
     */
    getStarAtPosition(x, y, getGridPosition) {
        if (!this.visible || !this.constellations) {
            return null;
        }

        // Check each constellation's stars
        for (const constellation of this.constellations) {
            for (const star of constellation.stars) {
                if (!star.visible) continue;
                
                const pos = getGridPosition(star.altitude, star.azimuth);
                if (!pos) continue;
                
                // Check if position matches
                if (pos.x === x && pos.y === y) {
                    return {
                        ...star,
                        constellation: constellation.name,
                        constellation_de: constellation.name_de
                    };
                }
            }
        }
        
        return null;
    }
}
