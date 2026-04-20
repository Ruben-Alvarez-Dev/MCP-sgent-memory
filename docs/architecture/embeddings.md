# Robust Embedding Validation

## Context
Our embedding system previously allowed vectors of different dimensions to pass through without validation. This could lead to silent data corruption in Qdrant collections where a single collection expects a fixed dimensionality (e.g., 1024 for BGE-M3).

## Improvements

### 1. Explicit Contract (`EmbeddingSpec`)
We introduced `EmbeddingSpec` to freeze the expected embedding configuration:
- **backend**: The provider used (llama_cpp, http, llama_server).
- **model_id**: The specific model name or path.
- **dim**: Required dimensionality (e.g., 1024).
- **metric**: Similarity metric (default: cosine).
- **version**: For future-proofing model migrations.

### 2. Strict Dimensionality Validation
Every backend call is now wrapped in `_validate_embedding_vector`. This function raises a `RuntimeError` if the returned vector does not match the dimension defined in `EMBEDDING_DIM`.

### 3. Strict Model Discovery
The `_discover_model` function now supports an `EMBEDDING_STRICT` mode. 
- When `EMBEDDING_STRICT=true` (default), it will only look for high-quality models (BGE-M3 or BGE variants).
- Generic `.gguf` fallbacks are disabled in strict mode to prevent accidental usage of low-quality or incompatible models.

## Environment Configuration
- `EMBEDDING_DIM`: Set this to the exact dimension your collection requires (default: 1024).
- `EMBEDDING_STRICT`: `true` to fail if no compatible model is found.
- `EMBEDDING_MODEL`: Override model name or path.
- `EMBEDDING_VERSION`: Model versioning for indexing consistency.
- `EMBEDDING_METRIC`: Similarity metric used by Qdrant (default: cosine).
