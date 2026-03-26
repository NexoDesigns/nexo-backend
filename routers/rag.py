"""
RAG search endpoint.

Primarily for testing and debugging from Swagger — lets you verify
that documents are being indexed and retrieved correctly before
relying on the automatic RAG injection in pipeline executions.
"""

from fastapi import APIRouter, Depends, HTTPException

from core.security import get_current_user_id
from models.document import RAGSearchRequest, RAGSearchResult
from services import rag_service

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/search", response_model=RAGSearchResult)
async def semantic_search(
    body: RAGSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Run a semantic search against the document knowledge base.

    Use this to verify:
    - Documents are being embedded correctly after upload.
    - The right chunks are being retrieved for a given query.
    - Similarity scores are reasonable (>0.7 is generally good).

    project_id is optional: if provided, results include both
    project-specific and global documents.
    """
    if body.top_k < 1 or body.top_k > 20:
        raise HTTPException(
            status_code=400,
            detail="top_k must be between 1 and 20",
        )

    results = await rag_service.search(
        query=body.query,
        project_id=body.project_id,
        type_filter=body.type_filter,
        top_k=body.top_k,
    )

    return RAGSearchResult(
        query=body.query,
        results=results,
        total=len(results),
    )