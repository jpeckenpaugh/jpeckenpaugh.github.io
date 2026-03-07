import colorsys
import json
import os
import re

def truecolor_fg(r, g, b):
    """Generates a 24-bit foreground ANSI escape code."""
    return f"\033[38;2;{r};{g};{b}m"

def hex_to_rgb(hex_code):
    """Converts a hex color string to an (r, g, b) tuple."""
    hex_code = hex_code.lstrip('#')
    if len(hex_code) != 6:
        return 0, 0, 0
    try:
        r = int(hex_code[0:2], 16)
        g = int(hex_code[2:4], 16)
        b = int(hex_code[4:6], 16)
        return r, g, b
    except ValueError:
        return 0, 0, 0

def _mix64(value: int) -> int:
    mask = 0xFFFFFFFFFFFFFFFF
    value = (value + 0x9E3779B97F4A7C15) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    return value ^ (value >> 31)

def _unit_from(value: int) -> float:
    return (_mix64(value) >> 11) / float(1 << 53)

def _random_band_ranges(band: int, random_config: dict) -> tuple[float, float, float, float]:
    bands = random_config.get("bands", {}) if isinstance(random_config, dict) else {}
    band_entry = bands.get(str(band), {}) if isinstance(bands, dict) else {}
    s_min = float(random_config.get("s_min", 0.4))
    s_max = float(random_config.get("s_max", 0.9))
    if isinstance(band_entry, dict):
        l_min = float(band_entry.get("l_min", 0.2))
        l_max = float(band_entry.get("l_max", 0.8))
        s_min = float(band_entry.get("s_min", s_min))
        s_max = float(band_entry.get("s_max", s_max))
    else:
        bright_min = float(random_config.get("l_bright_min", 0.75))
        bright_max = float(random_config.get("l_bright_max", 0.95))
        dark_min = float(random_config.get("l_dark_min", 0.18))
        dark_max = float(random_config.get("l_dark_max", 0.45))
        rank = band % 5
        t = rank / 4.0 if rank else 0.0
        l_min = bright_min + (dark_min - bright_min) * t
        l_max = bright_max + (dark_max - bright_max) * t
    l_min = max(0.0, min(1.0, l_min))
    l_max = max(l_min, min(1.0, l_max))
    s_min = max(0.0, min(1.0, s_min))
    s_max = max(s_min, min(1.0, s_max))
    return l_min, l_max, s_min, s_max

def sample_random_hex(band: int, sample_index: int, random_config: dict) -> tuple[str, tuple[int, int, int]]:
    l_min, l_max, s_min, s_max = _random_band_ranges(band, random_config)
    if band < 5:
        seed = (band * 0x9E3779B1) ^ (sample_index * 0x85EBCA77) ^ 0xC0FFEE
    else:
        seed = (band * 0x9E3779B1) ^ 0xC0FFEE
    h = _unit_from(seed)
    s = s_min + (_unit_from(seed + 1) * (s_max - s_min))
    l = l_min + (_unit_from(seed + 2) * (l_max - l_min))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    r_i, g_i, b_i = int(r * 255), int(g * 255), int(b * 255)
    return f"#{r_i:02X}{g_i:02X}{b_i:02X}", (r_i, g_i, b_i)

def display_color_map():
    """Reads colors.json and displays a visual map of the colors."""
    file_path = os.path.join(os.path.dirname(__file__), 'data', 'colors.json')
    
    try:
        with open(file_path, 'r') as f:
            colors = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find colors.json at {file_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not parse colors.json. Please check for syntax errors.")
        return

    # ANSI reset code
    reset = "\033[0m"

    print("\nLokarta Color Map Reference")
    print("===========================\n")
    
    # Sort keys alphabetically, ignoring case, lowercase first
    sorted_keys = sorted(colors.keys(), key=lambda k: (k.lower(), k.islower()))

    # Process lowercase letters first to establish pairs
    lower_keys = [k for k in sorted_keys if 'a' <= k <= 'z']
    
    # Group into columns for display
    num_columns = 4
    col_width = 26

    row_chunks = [lower_keys[i:i + num_columns] for i in range(0, len(lower_keys), num_columns)]

    for row in row_chunks:
        parts = []
        for key in row:
            upper_key = key.upper()

            soft_data = colors.get(key)
            intense_data = colors.get(upper_key)

            if not soft_data or not intense_data:
                continue

            soft_rgb = hex_to_rgb(soft_data["hex"])
            intense_rgb = hex_to_rgb(intense_data["hex"])

            soft_color_code = truecolor_fg(*soft_rgb)
            intense_color_code = truecolor_fg(*intense_rgb)

            soft_swatch = f"{soft_color_code}██{reset}"
            intense_swatch = f"{intense_color_code}██{reset}"

            top = f" {soft_swatch} {key}: {soft_data['name']}"
            bottom = f" {intense_swatch} {upper_key}: {intense_data['name']}"
            parts.append((top, bottom))

        if not parts:
            continue
        for line_index in range(2):
            line_to_print = ""
            for top, bottom in parts:
                line = top if line_index == 0 else bottom
                visible_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                padding = ' ' * max(0, (col_width - len(visible_line)))
                line_to_print += line + padding
            print(line_to_print.rstrip())
        print()

    random_config = colors.get("random") if isinstance(colors.get("random"), dict) else None
    if random_config:
        print("Random Bands (0-9)")
        print("-------------------")
        print("Digits 0-9 select a random color within a brightness band.")
        print("0-4 vary per pixel; 5-9 are stable per session. All vary across runs.")
        print()
        row = []
        for band in range(10):
            samples = [sample_random_hex(band, idx, random_config) for idx in range(1)]
            hex_code, rgb = samples[0]
            swatch = f"{truecolor_fg(*rgb)}██{reset}"
            row.append(f"{band}: {swatch} {hex_code}")
        print("  ".join(row[:5]))
        print("  ".join(row[5:]))
        print()

    if isinstance(colors.get("@"), dict) and colors.get("@", {}).get("name") == "gradient":
        print("Gradient Key")
        print("------------")
        print("@ uses the same diagonal gradient as the screen border.")
        print()

if __name__ == "__main__":
    display_color_map()
