from typing import Optional
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

class InputValue(BaseModel):
    value: str 
    unit: str

class CalculatorData(BaseModel):
    selectedFormulas: list[str]
    flowMethod: str
    pressure: InputValue
    flowRate: Optional[InputValue] = None
    mass: Optional[InputValue] = None
    time: Optional[InputValue] = None
    nozzleDiameter: Optional[InputValue] = None
    hoseLength: Optional[InputValue] = None

# --- Data Standardization Helpers ---
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

def get_diameter_in(input_val: Optional[InputValue]) -> float:
    if not input_val or not input_val.value: return 0.0
    val = to_float(input_val.value)
    return val * 0.0393701 if input_val.unit == "mm" else val

# --- Formulas ---
def calculate_nfpa(pressure_psi: float, flow_rate_gpm: float) -> float:
    # Example NFPA Formula (Reaction = 0.0505 * Q * sqrt(P))
    # Replace with your exact mathematical logic
    return 0.0505 * flow_rate_gpm * (pressure_psi ** 0.5)

def calculate_freeman(pressure_psi: float, diameter_in: float) -> float:
    # Example Freeman Formula (Reaction = 1.5 * d^2 * p)
    # Replace with your exact mathematical logic
    return 1.5 * (diameter_in ** 2) * pressure_psi

@app.post("/calculate-force")
async def calculate_force(data: CalculatorData):
    results = {}
    
    try:
        # Standardize core variables first
        pressure_psi = get_pressure_psi(data.pressure)
        flow_rate_gpm = get_flow_rate_gpm(data)
        
        for formula in data.selectedFormulas:
            if formula == "Standard (NFPA)":
                results[formula] = calculate_nfpa(pressure_psi, flow_rate_gpm)
            elif formula == "Freeman Formula":
                dia_in = get_diameter_in(data.nozzleDiameter)
                results[formula] = calculate_freeman(pressure_psi, dia_in)
            elif formula == "Modified Research":
                # Add your modified research logic here
                results[formula] = pressure_psi * 1.1 
                
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
            
    # Now returns {"results": {"Standard (NFPA)": 150.5, ...}}
    return {"results": results}