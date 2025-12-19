""" 
FastAPI Wrapper for Domain Comparable Search Agent
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uvicorn
from datetime import datetime

from src.agent.graph import create_agent_graph

app = FastAPI(
    title= "Domain Comparable Search API",
    description =" AI-powered domain comparable search using LangGraph",
    version = "1.0.0"
)

# Enable CORS(adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Initialize the LangGraph agent
agent_graph = None

class DomainSearchRequest(BaseModel):
    domain: str = Field(..., description="Domain name to search for comparables for", example="onepay.ai")
    
    class Config:
        json_schema_extra = {
            "example": {
                "domain": "onepay.ai"
            }
        }

class DomainSearchResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str

# API Endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize the agent on startup"""
    global agent_graph
    print("🚀 Initializing Domain Comparable Agent...")
    agent_graph = create_agent_graph()
    print("✅ Agent initialized successfully!")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Domain Comparable Search API",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "agent_loaded": agent_graph is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/v1/search", response_model=DomainSearchResponse)
async def search_comparables(request: DomainSearchRequest):
    """
    Search for comparable domains
    
    - **domain**: The domain name to find comparables for (e.g., "onepay.ai")
    
    Returns comparable domains with pricing, categories, and similarity scores.
    """
    try:
        if agent_graph is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        # Validate input
        if not request.domain or len(request.domain.strip()) == 0:
            raise HTTPException(status_code=400, detail="Domain cannot be empty")
        
        print(f"\n[API] Processing request for domain: {request.domain}")
        
        # Run the agent
        initial_state = {
            "input_domain": request.domain.strip()
        }
        
        result = agent_graph.invoke(initial_state)
        
        # Check for errors in result
        if result.get("error"):
            return DomainSearchResponse(
                success=False,
                data=None,
                error=result["error"],
                timestamp=datetime.utcnow().isoformat()
            )
        
        # Extract the result
        output = result.get("result", {})
        
        print(f"[API] Successfully processed {request.domain} - found {output.get('total_comparables', 0)} comparables")
        
        return DomainSearchResponse(
            success=True,
            data=output,
            error=None,
            timestamp=datetime.utcnow().isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/api/v1/batch-search")
async def batch_search_comparables(domains: list[str], background_tasks: BackgroundTasks):
    """
    Batch search for multiple domains (async processing)
    
    - **domains**: List of domain names to search
    
    Returns a job ID to track the batch processing.
    """
    if not domains or len(domains) == 0:
        raise HTTPException(status_code=400, detail="Domains list cannot be empty")
    
    # TODO: Implement async batch processing with job queue
    return {
        "message": "Batch processing not yet implemented",
        "domains_count": len(domains),
        "status": "pending"
    }

if __name__ == "__main__":
    # Run the API Server
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level = "info"
    )