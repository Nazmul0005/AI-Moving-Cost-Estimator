import os
import json
import time
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
import tempfile
import shutil
from dotenv import load_dotenv

load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Moving Cost Estimator API",
    description="AI-powered moving cost estimation from home videos",
    version="1.0.0"
)

# Initialize Gemini client
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# ============================================
# PYDANTIC MODELS
# ============================================

class VideoAnalysisRequest(BaseModel):
    """Request model for video analysis"""
    youtube_url: Optional[str] = Field(None, description="YouTube URL of home video")
    home_type: str = Field("apartment", description="Type of home: apartment or house")
    room_count: int = Field(3, description="Number of rooms")

class ItemInfo(BaseModel):
    """Item information"""
    name: str
    quantity: int
    size: str  # large, medium, small
    category: str  # furniture, appliance, box, other

class VideoAnalysisResponse(BaseModel):
    """Response model for video analysis"""
    items: List[ItemInfo]
    total_volume_cubic_feet: float
    needs_special_handling: List[str]

class CostEstimationRequest(BaseModel):
    """Request model for cost estimation"""
    items: List[ItemInfo]
    total_volume_cubic_feet: float
    needs_special_handling: List[str] = []
    distance_km: float
    origin_floor: int
    destination_floor: int
    has_elevator_origin: bool = False
    has_elevator_destination: bool = False

class CostBreakdown(BaseModel):
    """Cost breakdown"""
    labor: float
    truck: float
    fuel: float
    materials: float
    stairs_fee: float
    other: float

class CostEstimationResponse(BaseModel):
    """Response model for cost estimation"""
    total_cost: float
    cost_range: List[float]
    movers_needed: int
    truck_type: str
    estimated_hours: float
    breakdown: CostBreakdown
    special_notes: str = ""

# ============================================
# PRICING CONFIGURATION
# ============================================

PRICING_CONFIG = {
    "labor_rate_per_hour": 35,
    "truck_rates": {
        "small": 75,
        "medium": 120,
        "large": 180
    },
    "fuel_cost_per_km": 0.5,
    "stairs_fee_per_floor": 25,
    "packing_material_per_cubic_feet": 0.20,
    "base_hours": 4,
    "hour_per_100_cubic_feet": 0.5
}

# ============================================
# HELPER FUNCTIONS
# ============================================

def analyze_video_file(video_path: str, home_type: str, room_count: int) -> dict:
    """Analyze video and extract inventory"""
    
    prompt = f"""
Analyze this home moving video and create an inventory list.

Context:
- Home type: {home_type}
- Number of rooms: {room_count}

Instructions:
1. Identify ALL furniture, appliances, and household items visible in the video
2. Count the quantity of each item
3. Categorize size as: large, medium, or small
4. Categorize type as: furniture, appliance, box, or other
5. Estimate total volume in cubic feet
6. Flag any items needing special handling (piano, large wardrobe, fragile electronics, etc.)

Return ONLY a valid JSON object in this exact format (no markdown, no explanation):
{{
  "items": [
    {{"name": "sofa", "quantity": 1, "size": "large", "category": "furniture"}},
    {{"name": "dining table", "quantity": 1, "size": "large", "category": "furniture"}}
  ],
  "total_volume_cubic_feet": 800,
  "needs_special_handling": ["piano", "large_wardrobe"]
}}
"""
    
    try:
        # Check file size
        file_size = os.path.getsize(video_path)
        
        if file_size < 20 * 1024 * 1024:
            # Inline video for small files
            with open(video_path, 'rb') as f:
                video_bytes = f.read()
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=types.Content(
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                data=video_bytes,
                                mime_type='video/mp4'
                            )
                        ),
                        types.Part(text=prompt)
                    ]
                )
            )
        else:
            # Use File API for larger files
            myfile = client.files.upload(file=video_path)
            
            # Wait for file to be processed
            while myfile.state.name == "PROCESSING":
                time.sleep(2)
                myfile = client.files.get(name=myfile.name)
            
            if myfile.state.name == "FAILED":
                raise Exception(f"File processing failed: {myfile.name}")
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[myfile, prompt]
            )
        
        # Parse response
        result_text = response.text.strip()
        
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        inventory = json.loads(result_text)
        return inventory
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {str(e)}")


def analyze_youtube_video(youtube_url: str, home_type: str, room_count: int) -> dict:
    """Analyze YouTube video"""
    
    prompt = f"""
Analyze this home moving video and create an inventory list.

Context:
- Home type: {home_type}
- Number of rooms: {room_count}

Instructions:
1. Identify ALL furniture, appliances, and household items visible in the video
2. Count the quantity of each item
3. Categorize size as: large, medium, or small
4. Categorize type as: furniture, appliance, box, or other
5. Estimate total volume in cubic feet
6. Flag any items needing special handling (piano, large wardrobe, fragile electronics, etc.)

Return ONLY a valid JSON object in this exact format (no markdown, no explanation):
{{
  "items": [
    {{"name": "sofa", "quantity": 1, "size": "large", "category": "furniture"}},
    {{"name": "dining table", "quantity": 1, "size": "large", "category": "furniture"}}
  ],
  "total_volume_cubic_feet": 800,
  "needs_special_handling": ["piano", "large_wardrobe"]
}}
"""
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=types.Content(
                parts=[
                    types.Part(
                        file_data=types.FileData(file_uri=youtube_url)
                    ),
                    types.Part(text=prompt)
                ]
            )
        )
        
        result_text = response.text.strip()
        
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        inventory = json.loads(result_text)
        return inventory
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"YouTube video analysis failed: {str(e)}")


def calculate_cost(inventory: dict, distance_km: float, origin_floor: int, 
                  destination_floor: int, has_elevator_origin: bool, 
                  has_elevator_destination: bool) -> dict:
    """Calculate moving cost"""
    
    prompt = f"""
Analyze this moving inventory and provide intelligent estimates.

Inventory:
{json.dumps(inventory, indent=2)}

Move Details:
- Distance: {distance_km} km
- Origin floor: {origin_floor} (Elevator: {has_elevator_origin})
- Destination floor: {destination_floor} (Elevator: {has_elevator_destination})

Based on the items, especially heavy/special items, provide:
1. Recommended number of movers (2-6 people)
2. Truck type needed: small (up to 400 cubic feet), medium (400-900), large (900+)
3. Additional hours needed beyond base time due to item complexity
4. Any special handling notes

Return ONLY a valid JSON object:
{{
  "recommended_movers": 3,
  "truck_type": "medium",
  "complexity_hours_add": 1.5,
  "special_notes": "Piano requires extra care and time"
}}
"""
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        result_text = response.text.strip()
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        ai_estimate = json.loads(result_text)
        
    except Exception as e:
        # Fallback to simple rules
        volume = inventory.get('total_volume_cubic_feet', 500)
        ai_estimate = {
            "recommended_movers": 2 if volume < 400 else (3 if volume < 800 else 4),
            "truck_type": "small" if volume < 400 else ("medium" if volume < 900 else "large"),
            "complexity_hours_add": len(inventory.get('needs_special_handling', [])) * 0.5,
            "special_notes": ""
        }
    
    # Calculate costs
    volume = inventory.get('total_volume_cubic_feet', 500)
    movers = ai_estimate['recommended_movers']
    truck_type = ai_estimate['truck_type']
    
    # Time estimation
    base_hours = PRICING_CONFIG['base_hours']
    volume_hours = (volume / 100) * PRICING_CONFIG['hour_per_100_cubic_feet']
    complexity_hours = ai_estimate.get('complexity_hours_add', 0)
    estimated_hours = round(base_hours + volume_hours + complexity_hours, 1)
    
    # Labor cost
    labor_cost = round(movers * estimated_hours * PRICING_CONFIG['labor_rate_per_hour'], 2)
    
    # Truck cost
    truck_base = PRICING_CONFIG['truck_rates'][truck_type]
    fuel_cost = round(distance_km * PRICING_CONFIG['fuel_cost_per_km'], 2)
    
    # Stairs fee
    stairs_floors = 0
    if not has_elevator_origin and origin_floor > 1:
        stairs_floors += (origin_floor - 1)
    if not has_elevator_destination and destination_floor > 1:
        stairs_floors += (destination_floor - 1)
    stairs_fee = stairs_floors * PRICING_CONFIG['stairs_fee_per_floor']
    
    # Materials
    materials_cost = round(volume * PRICING_CONFIG['packing_material_per_cubic_feet'], 2)
    
    # Other fees
    other_fees = round((labor_cost + truck_base + fuel_cost) * 0.05, 2)
    
    # Total
    total_cost = round(labor_cost + truck_base + fuel_cost + stairs_fee + materials_cost + other_fees, 2)
    
    # Cost range
    cost_min = round(total_cost * 0.9, 2)
    cost_max = round(total_cost * 1.1, 2)
    
    return {
        "total_cost": total_cost,
        "cost_range": [cost_min, cost_max],
        "movers_needed": movers,
        "truck_type": truck_type,
        "estimated_hours": estimated_hours,
        "breakdown": {
            "labor": labor_cost,
            "truck": truck_base,
            "fuel": fuel_cost,
            "materials": materials_cost,
            "stairs_fee": stairs_fee,
            "other": other_fees
        },
        "special_notes": ai_estimate.get('special_notes', '')
    }


# ============================================
# API ENDPOINTS
# ============================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Moving Cost Estimator API",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/v1/analyze-video": "Analyze video and get inventory",
            "POST /api/v1/estimate-cost": "Calculate moving cost from inventory"
        }
    }

@app.post("/api/v1/analyze-video", response_model=VideoAnalysisResponse)
async def analyze_video_endpoint(
    video_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    home_type: str = Form("apartment"),
    room_count: int = Form(3)
):
    """
    Stage 1: Analyze home video and extract inventory
    
    - Upload a video file OR provide a YouTube URL
    - Returns list of items, quantities, and total volume
    """
    
    if not video_file and not youtube_url:
        raise HTTPException(
            status_code=400, 
            detail="Either video_file or youtube_url must be provided"
        )
    
    try:
        if youtube_url:
            # Analyze YouTube video
            inventory = analyze_youtube_video(youtube_url, home_type, room_count)
        else:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
                shutil.copyfileobj(video_file.file, temp_file)
                temp_path = temp_file.name
            
            try:
                # Analyze uploaded video
                inventory = analyze_video_file(temp_path, home_type, room_count)
            finally:
                # Clean up temp file
                os.unlink(temp_path)
        
        return VideoAnalysisResponse(**inventory)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/estimate-cost", response_model=CostEstimationResponse)
async def estimate_cost_endpoint(request: CostEstimationRequest):
    """
    Stage 2: Calculate moving cost based on inventory
    
    - Takes inventory from Stage 1
    - Returns detailed cost breakdown
    """
    
    try:
        # Convert request to inventory dict
        inventory = {
            "items": [item.dict() for item in request.items],
            "total_volume_cubic_feet": request.total_volume_cubic_feet,
            "needs_special_handling": request.needs_special_handling
        }
        
        # Calculate cost
        cost_data = calculate_cost(
            inventory,
            request.distance_km,
            request.origin_floor,
            request.destination_floor,
            request.has_elevator_origin,
            request.has_elevator_destination
        )
        
        return CostEstimationResponse(**cost_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "moving-cost-estimator"}


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)