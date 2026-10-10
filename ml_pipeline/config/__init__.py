# Regional Constants for Pune, Maharashtra
# Data sourced from IMD (India Meteorological Department) and regional soil surveys

CONFIG = {
    # --- Hydrology (Flood Risk) ---
    # Curve Numbers (SCS-CN) for typical Pune soils (mostly Black Cotton/Alluvial)
    'curve_numbers': {
        'vegetation': 60,   # Good condition grassland/forest
        'impervious': 98,   # Pavement/Roof
        'water': 100,       # Open water
    },
    # 24-hour Design Storm for Pune (approx 100-year return period)
    'design_storm_mm': 150.0,

    # --- Thermal (Heat Island) ---
    # Urban Heat Island (UHI) intensity factor for Pune
    'uhi_intensity_factor': 0.15,
    'base_temp_celsius': 28.0,

    # --- Carbon (Embodied Carbon) ---
    # Emission factors (kg CO2e per kg of material) - Based on GRIHA/Industry standards
    'emission_factors_kgco2e_per_kg': {
        'concrete_ready_mix': 0.15,
        'steel_reinforcement': 1.85,
        'brick': 0.24,
        'glass': 1.20,
        'aluminium': 12.5,
    },
    # Carbon intensity bands (kg CO2e per sqm of built-up area)
    'carbon_bands': {
        'low': 400,
        'moderate': 800,
        'high': 1200,
    },

    # --- Weighting for Composite Score ---
    'weights': {
        'flood': 0.30,
        'heat': 0.30,
        'green': 0.20,
        'carbon': 0.20
    }
}

# Validate weights
if abs(sum(CONFIG['weights'].values()) - 1.0) >= 1e-6:
    raise ValueError("Weights in CONFIG must sum to 1.0")
