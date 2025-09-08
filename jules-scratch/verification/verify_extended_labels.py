import re
from playwright.sync_api import sync_playwright, expect

def run_verification(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # 1. Navigate to the application
        page.goto("http://localhost:8001", timeout=60000)

        # 2. Wait for the API call to finish and the sky to be rendered
        with page.expect_response(re.compile(r'/api/celestial')):
            print("Waiting for celestial API response...")
        print("Celestial API response received.")

        # Wait for an asteroid symbol to appear
        asteroid_symbol = '⚸'
        sky_text_element = page.locator("#sky-container .sky-text")
        expect(sky_text_element).to_contain_text(asteroid_symbol, timeout=15000)
        print("Asteroid symbol found in sky view.")

        # 3. Find the coordinates of the first asteroid symbol
        sky_text_content = sky_text_element.inner_text()
        lines = sky_text_content.split('\\n')

        asteroid_row = -1
        asteroid_col = -1
        for i, line in enumerate(lines):
            col = line.find(asteroid_symbol)
            if col != -1:
                asteroid_row = i
                asteroid_col = col
                break

        if asteroid_row == -1:
            raise Exception(f"Asteroid symbol '{asteroid_symbol}' not found.")

        # 4. Calculate the pixel coordinates and click
        sky_rect = sky_text_element.bounding_box()
        col_width = sky_rect['width'] / len(lines[0])
        row_height = sky_rect['height'] / len(lines)

        click_x = sky_rect['x'] + (asteroid_col + 0.5) * col_width
        click_y = sky_rect['y'] + (asteroid_row + 0.5) * row_height

        page.click("#sky-container .sky-text", position={'x': click_x - sky_rect['x'], 'y': click_y - sky_rect['y']}, force=True)
        print("Clicked on the first asteroid found.")

        # 5. Verify the dialog appears and get the asteroid's name from it
        dialog = page.locator("#object-dialog")
        expect(dialog).to_be_visible(timeout=5000)

        # The first line of the dialog content should be the name
        dialog_content = dialog.inner_text()
        # The name is usually after the symbol, e.g., "⚸ Vesta"
        name_from_dialog_match = re.search(r'⚸\s*([^\n]+)', dialog_content)
        if not name_from_dialog_match:
            raise Exception("Could not extract asteroid name from dialog.")

        name_from_dialog = name_from_dialog_match.group(1).strip()
        print(f"Name from dialog: {name_from_dialog}")

        # 6. Verify that the in-sky label matches the name from the dialog
        # The label format is "NAME (-XX.X°)"
        # We need to handle special characters in the name for the regex
        # The displayed name in the sky might be the cleaned-up version. Let's use that.
        cleaned_name_from_dialog = name_from_dialog.split('(')[0].strip()
        name_regex = re.escape(cleaned_name_from_dialog)
        expect(sky_text_element).to_contain_text(re.compile(f'{name_regex} \\(-?\\d+\\.\\d+°\\)'), timeout=5000)
        print(f"Successfully verified in-sky label for '{name_from_dialog}'.")

        # 7. Take the final screenshot
        page.screenshot(path="jules-scratch/verification/verification.png")
        print("Final screenshot taken.")

    except Exception as e:
        print(f"An error occurred during verification: {e}")
        page.screenshot(path="jules-scratch/verification/verification_error.png")
    finally:
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as p:
        run_verification(p)
