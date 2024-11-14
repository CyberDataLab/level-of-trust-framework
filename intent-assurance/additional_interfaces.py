import httpx
from fastapi import APIRouter, HTTPException

# Create a router instance to include interfaces to main Swager API from other files
router = APIRouter()

@router.get("/api/trust_management", tags=["api"], summary="Trust Management Function")
async def trust_management_route():
    # Currently, we only have 1 monitoring agents instance and 1 node
    url = "http://127.0.0.1:8000/trust_management_LoTAF"  # Assuming it's running locally
    params = {}

    # Use httpx to make the GET request
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

        # Check for HTTP errors
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Error retrieving trust scores")

        # Parse the response to a list of dictionaries
        return response.json()
