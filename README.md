# ASCII Sky - Moon Tracker

A simple web application that displays the current moon phase and position in ASCII art, specifically for Vienna, Austria.

## Features

- Real-time moon position tracking (altitude and azimuth)
- Current moon phase visualization in ASCII art
- Distance to moon calculation
- Auto-updates every 30 seconds
- Responsive design

## Prerequisites

- Docker and Docker Compose

## Running the Application

### Using Docker Compose (Recommended)

1. Clone this repository
2. Navigate to the project directory
3. Run the following command:
   ```bash
   docker-compose up --build
   ```
4. Open your browser and navigate to `http://localhost:8000`

### Without Docker

1. Ensure you have Python 3.9+ installed
2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   uvicorn main:app --reload
   ```
4. Open your browser and navigate to `http://localhost:8000`

## Project Structure

- `main.py` - FastAPI application with moon calculation logic
- `templates/` - HTML templates
- `static/` - Static files (CSS, JS, images)
- `Dockerfile` - Docker configuration
- `docker-compose.yml` - Docker Compose configuration
- `requirements.txt` - Python dependencies

## Technologies Used

- Backend: FastAPI, Skyfield
- Frontend: HTML, CSS, JavaScript
- Containerization: Docker, Docker Compose

## Attribution

This project was built with assistance from Windsurf (agentic AI coding assistant) and SWE-1. Babysitting by a human in a virtual environment.

## License

This repository is released under the MIT License. See the LICENSE file for the full text.

# asciisky
