"""
Parser Service - FastAPI Application.
Provides HTTP endpoints for instruction parsing using existing VLM/RAG system.
"""
import asyncio
import sys
import os
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.shared.config import get_parser_config, get_service_config
from services.shared.models import ParseResult, HealthResponse
from services.shared.utils import ServiceLogger, format_error_response
from services.parser_service.converter import PortInstructionConverter


# Parse request model
class ParseRequest(BaseModel):
    """Request model for parse endpoint."""
    text: Optional[str] = Field(None, description="Text input to parse")
    image_path: Optional[str] = Field(None, description="Path to image file")
    audio_path: Optional[str] = Field(None, description="Path to audio file")
    use_rag: Optional[bool] = Field(None, description="Override RAG setting")


# Global state
config = get_parser_config()
service_config = get_service_config()
logger = ServiceLogger.get_logger(config.service_name, config.log_level)
converter = PortInstructionConverter()

# Service uptime tracking
start_time = time.time()

# VLM Parser instance (lazy loaded)
_vlm_parser = None


def get_vlm_parser():
    """Lazy load VLM parser."""
    global _vlm_parser
    if _vlm_parser is None:
        try:
            from src.vlm import get_vlm_instance
            from src.parser import PortInstructionParser

            logger.info("Initializing VLM parser...")
            vlm = get_vlm_instance()
            instruction_parser = PortInstructionParser()
            _vlm_parser = {"vlm": vlm, "parser": instruction_parser}
            logger.info("VLM parser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize VLM parser: {e}")
            _vlm_parser = "error"
    return _vlm_parser


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info(f"Starting {config.service_name} on {config.host}:{config.port}")

    # Initialize VLM parser on startup
    if config.use_rag or True:  # Always try to initialize
        parser = get_vlm_parser()
        if parser == "error":
            logger.warning("VLM parser initialization failed, service may have limited functionality")

    yield

    logger.info(f"Shutting down {config.service_name}")


# Create FastAPI app
app = FastAPI(
    title="Parser Service",
    description="Instruction parsing service for warehouse scheduling system",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    uptime = time.time() - start_time

    dependencies = {}
    parser = get_vlm_parser()
    if parser == "error":
        dependencies["vlm"] = "error"
    elif parser is None:
        dependencies["vlm"] = "initializing"
    else:
        dependencies["vlm"] = "ok"

    return HealthResponse(
        status="ok" if parser != "error" else "degraded",
        service=config.service_name,
        uptime_seconds=uptime,
        dependencies=dependencies,
    )


@app.post("/api/v1/parse")
async def parse_instruction(request: ParseRequest):
    """
    Parse instruction into WarehouseTask.

    Accepts text, image, or audio input and returns a structured WarehouseTask.
    """
    try:
        logger.info(f"Parse request received: text={request.text is not None}, "
                   f"image={request.image_path is not None}, "
                   f"audio={request.audio_path is not None}")

        # Get VLM parser
        parser_obj = get_vlm_parser()

        if parser_obj == "error":
            raise HTTPException(
                status_code=503,
                detail="VLM parser not available. Please check service configuration."
            )

        vlm = parser_obj["vlm"]
        instruction_parser = parser_obj["parser"]

        # Prepare raw input
        raw_input = request.text or ""

        # Process based on input type
        if request.audio_path:
            logger.info(f"Processing audio file: {request.audio_path}")
            # Transcribe audio using ASR
            from src.asr import get_asr_instance
            asr = get_asr_instance()
            raw_input = asr.transcribe_file(request.audio_path)
            logger.info(f"Transcribed text: {raw_input}")

        elif request.image_path:
            logger.info(f"Processing image file: {request.image_path}")
            # Extract text from image using VLM
            from PIL import Image
            image = Image.open(request.image_path)
            vlm_result = vlm.extract_structured_info(
                text=raw_input or "请识别图像中的内容",
                image=image
            )

        elif request.text:
            logger.info(f"Processing text: {request.text[:100]}")
            # Process text directly
            vlm_result = vlm.extract_structured_info(text=request.text)

        else:
            raise HTTPException(
                status_code=400,
                detail="At least one of text, image_path, or audio_path must be provided"
            )

        # Parse VLM result into PortInstruction
        instruction = instruction_parser.parse_output(
            vlm_result,
            raw_text=raw_input
        )

        # Convert to WarehouseTask
        task = converter.convert(instruction, raw_input)

        # Return parse result
        return ParseResult(
            task=task,
            raw_input=raw_input,
            confidence=vlm_result.get("confidence", 1.0) if isinstance(vlm_result, dict) else 1.0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing instruction: {e}", exc_info=True)
        error_response = format_error_response(e, config.service_name)
        return JSONResponse(
            status_code=500,
            content=error_response
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": config.service_name,
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "parse": "/api/v1/parse",
            "docs": "/docs"
        }
    }


def main():
    """Run the parser service."""
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=service_config.debug,
    )


if __name__ == "__main__":
    main()
