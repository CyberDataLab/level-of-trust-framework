from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from additional_interfaces import router as trust_management_router  # Import router from Trust_Management_System
from typing import List
import httpx
import uvicorn
import pyarrow.csv as pv
import pyarrow.compute as pc
import pyarrow as pa


# Initialize the FastAPI app
app = FastAPI(
    title="Level of Trust Assessment Function API",
    description="This API describes services offered by LoTAF",
    version="1.0.0",
    contact={
        "name": "Jose Maria Jorquera Valero",
        "url": "https://cyberdatalab.um.es/josemaria-jorquera/",
        "email": "josemaria.jorquera@um.es",
    },
)

path = ""

# Define the Pydantic model for the response of /trust_management_LoTAF
class Trust_Score_Response(BaseModel):
    # Assuming it returns a list of dictionaries
    id: str
    trust_index: float

    class Config:
        json_schema_extra = {
                "id": "uuid1",
                "trust_index": 0.4
        }

# Define the FastAPI route to expose the retrieve_trust_scores method
@app.get("/trust_management_LoTAF", response_model=List[Trust_Score_Response], tags=["monitoring"], summary="Get trust scores", description="Retrieve trust scores from the available computation nodes")
async def get_trust_scores():
    # Obtain the trust scores and return the result
    try:
        # Read the CSV file into PyArrow Table
        table = pv.read_csv("/tmp/scores.csv")

        # Compute the mean for each column in table
        means = {}
        for column in table.column_names:
            if pa.types.is_integer(table[column].type):
                mean_value = pc.mean(table[column])
                means[column] = mean_value.as_py() # Convert to Python native type

        # Compute the final trust score
        mean_trust_score = 0
        active_dimension_number = 0

        for column, mean, in means.items():
            if mean != 0.0:
                mean_trust_score += mean
                active_dimension_number +=1

        mean_trust_score = (mean_trust_score / active_dimension_number)/100

        return [{"id": str(table["ID"][1]), "trust_index": float(mean_trust_score)}]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Include the router from Trust_Management_System.py
app.include_router(trust_management_router)


# Entry point for running the app
if __name__ == "__main__":
    # This will allow the FastAPI app to be launched as a standalone application
    uvicorn.run("trust_score_response:app", host="127.0.0.1", port=8000, reload=True)