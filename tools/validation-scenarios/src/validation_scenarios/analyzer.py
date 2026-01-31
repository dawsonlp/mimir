"""Multi-perspective document analyzer.

Analyzes documents from multiple perspectives using LLM,
stores results as artifacts in Mímir with derived_from relations.
"""

from uuid import UUID

from validation_scenarios.llm import analyze, get_model_info
from validation_scenarios.mimir_client import MimirClient


# Perspective definitions: (artifact_type, prompt_template)
PERSPECTIVES = {
    "summary": (
        "summary",
        """Summarize the following document in 2-3 clear paragraphs. 
Focus on the main points, key arguments, and overall message.

Document:
{content}""",
    ),
    "findings": (
        "finding",
        """Extract the key findings, facts, and statistics from this document.
List them as bullet points, focusing on concrete, verifiable information.

Document:
{content}""",
    ),
    "questions": (
        "question",
        """What important questions does this document raise?
What aspects need clarification or further investigation?
List the most significant questions this content prompts.

Document:
{content}""",
    ),
    "analysis": (
        "analysis",
        """Provide a critical analysis of this document.
Consider: strengths, weaknesses, assumptions made, potential biases,
and how well the arguments are supported.

Document:
{content}""",
    ),
    "insights": (
        "conclusion",
        """What are the actionable insights and practical takeaways from this document?
What should the reader do or consider based on this information?

Document:
{content}""",
    ),
}


def get_available_perspectives() -> list[str]:
    """Return list of available perspective names."""
    return list(PERSPECTIVES.keys())


async def analyze_document(
    client: MimirClient,
    document_id: UUID,
    content: str,
    title: str,
    perspectives: list[str] | None = None,
) -> list[dict]:
    """Analyze a document from multiple perspectives.
    
    Creates analysis artifacts and derived_from relations for each perspective.
    
    Args:
        client: MimirClient instance
        document_id: UUID of the source document artifact
        content: Document content to analyze
        title: Document title (for naming analyses)
        perspectives: List of perspective names. If None, uses all.
    
    Returns:
        List of created artifact dicts with relation info
    """
    if perspectives is None:
        perspectives = list(PERSPECTIVES.keys())
    
    # Validate perspectives
    invalid = set(perspectives) - set(PERSPECTIVES.keys())
    if invalid:
        raise ValueError(f"Unknown perspectives: {invalid}. Available: {list(PERSPECTIVES.keys())}")
    
    model_info = get_model_info()
    results = []
    
    for perspective_name in perspectives:
        artifact_type, prompt_template = PERSPECTIVES[perspective_name]
        
        # Run LLM analysis
        analysis_content = await analyze(content, prompt_template)
        
        # Create analysis artifact
        artifact = await client.create_artifact(
            artifact_type=artifact_type,
            title=f"{title} - {perspective_name.title()}",
            content=analysis_content,
            source="generated",
            source_system="validation-scenarios",
            metadata={
                "perspective": perspective_name,
                "source_document_id": str(document_id),
                "llm_provider": model_info["provider"],
                "llm_model": model_info["model"],
            },
        )
        
        # Create derived_from relation (analysis -> document)
        relation = await client.create_relation(
            source_id=UUID(artifact["id"]),
            target_id=document_id,
            relation_type="derived_from",
            confidence=1.0,
            metadata={
                "perspective": perspective_name,
                "generated_by": "validation-scenarios",
            },
        )
        
        results.append({
            "perspective": perspective_name,
            "artifact": artifact,
            "relation": relation,
        })
    
    return results


async def ingest_file(
    client: MimirClient,
    file_path: str,
    content: str,
    analyze_perspectives: list[str] | None = None,
) -> dict:
    """Ingest a file and optionally analyze it.
    
    Args:
        client: MimirClient instance
        file_path: Path to the file (used for title/metadata)
        content: File content
        analyze_perspectives: Perspectives to analyze. None = skip analysis.
    
    Returns:
        Dict with document artifact and optional analysis results
    """
    import os
    
    filename = os.path.basename(file_path)
    
    # Create document artifact
    document = await client.create_artifact(
        artifact_type="document",
        title=filename,
        content=content,
        source="import",
        source_system="file",
        external_id=file_path,
        metadata={
            "filename": filename,
            "file_path": file_path,
        },
    )
    
    result = {"document": document, "analyses": []}
    
    # Optionally analyze
    if analyze_perspectives:
        analyses = await analyze_document(
            client=client,
            document_id=UUID(document["id"]),
            content=content,
            title=filename,
            perspectives=analyze_perspectives,
        )
        result["analyses"] = analyses
    
    return result