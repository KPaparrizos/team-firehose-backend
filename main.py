from typing import Optional
import numpy as np
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Physical constants:
RHO = 1.94 # Fluid density of water in slugs/ft^3 at ~60-70 F
G = 32.174 # Acceleration due to gravity in ft/s^2

# Unit conversion constants:
FT_TO_IN = 12
MIN_TO_S = 60
FT3_TO_GAL = 7.48052

# Pydantic models for input validation
class InputValue(BaseModel):
    value: str 
    unit: str

class CalculatorData(BaseModel):
    selectedFormulas: list[str]
    flowMethod: str
    pressure: Optional[InputValue] = None
    flowRate: Optional[InputValue] = None
    flowMassChange: Optional[InputValue] = None
    flowTime: Optional[InputValue] = None
    nozzleDiameter: Optional[InputValue] = None
    hoseDiameter: Optional[InputValue] = None
    kickbackMassChange: Optional[InputValue] = None
    rodLength: Optional[InputValue] = None
    wheelRadius: Optional[InputValue] = None

# Data standardization helpers
def to_float(val_str: str) -> float:
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0

def get_pressure_psi(input_val: InputValue) -> float:
    val = to_float(input_val.value)
    return val * 14.5038 if input_val.unit == "bar" else val

def get_flow_rate_gpm(data: CalculatorData) -> float:
    # Handle Direct Input
    if data.flowMethod == "direct" and data.flowRate:
        val = to_float(data.flowRate.value)
        return val * 0.264172 if data.flowRate.unit == "lpm" else val
        
    # Handle Mass/Time Input
    elif data.flowMethod == "mass-time" and data.mass and data.time:
        mass_val = to_float(data.mass.value)
        mass_lbs = mass_val * 2.20462 if data.mass.unit == "kg" else mass_val
        
        time_val = to_float(data.time.value)
        time_mins = time_val / 60.0 if data.time.unit == "sec" else time_val
        
        # 1 Gallon of water = ~8.34 lbs
        gallons = mass_lbs / 8.34
        return gallons / time_mins if time_mins > 0 else 0.0
        
    return 0.0

def get_length_in(input_val: Optional[InputValue]) -> float:
    if not input_val or not input_val.value: return 0.0
    val = to_float(input_val.value)
    return val * 0.0393701 if input_val.unit == "mm" else val

def get_mass_lb(input_val: Optional[InputValue]) -> float:
    if not input_val or not input_val.value: return 0.0
    val = to_float(input_val.value)
    return val * 0.0393701 if input_val.unit == "kg" else val


# Formulas
def calculate_actual(rod_length_in: float, wheel_radius_in: float, mass_change_lb) -> float:
    # Formula: mg * ((r + w) / w) (where r is rod length, w is wheel radius)
    # Inches from rod_length/wheel_radius should cancel, resulting in lbf
    return ((rod_length_in + wheel_radius_in) / wheel_radius_in) * G  * mass_change_lb 

def calculate_nfpa(pressure_psi: float, nozzle_diameter_in: float) -> float:
    # Formula: 1.57 * d^2 * p
    # Inches from nozzle_diameter cancel out with inches from pressure, resulting in lbf
    return 1.57 * (nozzle_diameter_in ** 2) * pressure_psi

def calculate_chin_7 (flow_rate_gpm: float, nozzle_diameter_in: float) -> float:
    # Formula: ρ * Q^2​ / A2^2 
    # After unit conversions, result should be dimensionally consistent and in lbf
    return RHO * (((flow_rate_gpm / FT3_TO_GAL) / MIN_TO_S) ** 2) / (np.pi * (((nozzle_diameter_in / FT_TO_IN)) / 2) ** 2)

def calculate_chin_10 (pressure_psi: float, hose_diameter_in, nozzle_diameter_in: float) -> float:
    # Formula: 2 * p * A2 / (1 - (A2 / A1)^2)
    # Inches from nozzle_diameter cancel out with inches from pressure, resulting in lbf
    return 2 * pressure_psi * (np.pi * ((nozzle_diameter_in / 2) ** 2)) / (1 - ((np.pi * ((nozzle_diameter_in / 2) ** 2)) 
                                                                                / (np.pi * ((hose_diameter_in / 2) ** 2))) ** 2)

def calculate_chin_11 (flow_rate_gpm: float, pressure_psi: float, hose_diameter_in: float) -> float:
    # Formula: sqrt(2 * ρ * Q^2 * p + (ρ^2 * Q^4) / A1^2)
    # After unit conversions, result should be dimensionally consistent and in lbf
    return np.sqrt(2 * RHO * (((flow_rate_gpm / FT3_TO_GAL) / MIN_TO_S) ** 2) * (pressure_psi * (FT_TO_IN ** 2)) + ((RHO ** 2) * (((flow_rate_gpm / FT3_TO_GAL) / MIN_TO_S) ** 4)) 
                   / ((np.pi * (((hose_diameter_in / FT_TO_IN) / 2) ** 2))) ** 2)

# FastAPI request functions
#TODO: Add a case statement so we can check which data helpers we need to use, don't call any multiple times
#TODO: Convert units before returning results
#TODO: Let user select which units they want the output to be in as well
@app.post("/calculate-force")
async def calculate_force(data: CalculatorData):
    results = {}
    
    try:
        # Loop through all selected formulas and calculate, storing results in result dictionary
        for formula in data.selectedFormulas:
            if formula == "Experimental (Actual)":
                rod_length_in = get_length_in(data.rodLength)
                wheel_radius_in = get_length_in(data.wheelRadius)
                kickback_mass_change_lb = get_mass_lb(data.kickbackMassChange)

                results[formula] = calculate_actual(rod_length_in, wheel_radius_in, kickback_mass_change_lb)
            elif formula == "NFPA Equation":
                pressure_psi = get_pressure_psi(data.pressure)
                nozzle_diameter_in = get_length_in(data.nozzleDiameter)

                results[formula] = calculate_nfpa(pressure_psi, nozzle_diameter_in)
            elif formula == "Chin et al. Equation (7)":
                flow_rate_gpm = get_flow_rate_gpm(data)
                nozzle_diameter_in = get_length_in(data.nozzleDiameter)

                results[formula] = calculate_chin_7(flow_rate_gpm, nozzle_diameter_in)
            elif formula == "Chin et al. Equation (10)":
                pressure_psi = get_pressure_psi(data.pressure)
                hose_diameter_in = get_length_in(data.hoseDiameter)
                nozzle_diameter_in = get_length_in(data.nozzleDiameter)

                results[formula] = calculate_chin_10(pressure_psi, hose_diameter_in, nozzle_diameter_in)
            elif formula == "Chin et al. Equation (11)":
                flow_rate_gpm = get_flow_rate_gpm(data)
                pressure_psi = get_pressure_psi(data.pressure)
                hose_diameter_in = get_length_in(data.hoseDiameter)

                results[formula] = calculate_chin_11(flow_rate_gpm, pressure_psi, hose_diameter_in)
                
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
            
    # Returns {"results": {"Experimental (Actual)": 150.5, ...}}
    return {"results": results}