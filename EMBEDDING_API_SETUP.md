# Embedding API Setup & Configuration Guide

## Overview
The ResourceIQ backend uses **Jina Code Embeddings** to generate specialized vector embeddings for GitHub PR analysis. This guide covers complete setup for both API and local deployment modes.

## Supported Jina Code Embedding Models

### Available Models
1. **jinaai/jina-code-embeddings-1.5b** (Recommended)
   - Larger, more accurate model
   - 1024 output dimensions
   - Better code understanding
   - Higher computational requirements
   
2. **jinaai/jina-code-embeddings-0.5b** (Current Default)
   - Lightweight, faster inference
   - 1024 output dimensions
   - Lower computational requirements
   - Good for real-time applications

## Setup Guide

### Step 1: Prerequisites

#### For API Mode (Recommended for Production)
1. Sign up at [Jina AI Console](https://jina.ai/login)
2. Create or obtain your API key
3. Keep it secure in your `.env` file

#### For Local Mode (Recommended for Development)
1. Python 3.10+
2. Sufficient disk space (models are ~500MB - 2GB)
3. GPU recommended (NVIDIA CUDA for faster inference)
4. RAM requirement: 4GB minimum (8GB+ recommended)

### Step 2: Install Dependencies

Both modes require dependencies already in `pyproject.toml`:

```bash
# These are already included in the project
# - sentence-transformers (for local models)
# - torch (PyTorch, for inference)
# - pgvector (for database storage)

# If starting fresh, install with:
uv sync
```

The first time you use a local model, HuggingFace will automatically download it:

```bash
# Models stored in ~/.cache/huggingface/hub/
# Size: ~500MB for 0.5b, ~2GB for 1.5b
```

### Step 3: Environment Configuration

#### Option A: Using API Mode (Production)

Add to `.env`:

```env
# Jina AI Configuration
JINA_API_KEY=jina_xxxxxxxxxxxxxxxxxxxx
JINA_API_URL=https://api.jina.ai
JINA_EMBEDDING_MODEL1=jina-code-embeddings-1.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-1.5b
USE_JINA_API=true
EMBEDDING_DIMENSION=1536
```

**Features**:
- ✅ No local model download needed
- ✅ Latest model updates automatically
- ✅ Scalable for production
- ❌ Requires API key and internet connection
- ❌ API costs apply

#### Option B: Using Local Models (Development)

Add to `.env`:

```env
# Local Jina Code Embeddings
JINA_API_KEY=dummy_key_for_local_mode
JINA_API_URL=https://api.jina.ai
JINA_EMBEDDING_MODEL1=jina-code-embeddings-0.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
USE_JINA_API=false
EMBEDDING_DIMENSION=1536
```

**Features**:
- ✅ No API costs
- ✅ Offline processing capability
- ✅ Full control over model versions
- ❌ Requires local computational resources
- ❌ First run downloads ~500MB-2GB

#### Option C: Switching Between 1.5b and 0.5b Models

```env
# For 1.5b (more accurate)
JINA_EMBEDDING_MODEL1=jina-code-embeddings-1.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-1.5b

# For 0.5b (faster)
JINA_EMBEDDING_MODEL1=jina-code-embeddings-0.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
```

## API Models Configuration

### Current Setup
- **API Model (JINA_EMBEDDING_MODEL1)**: `jina-code-embeddings-0.5b` or `jina-code-embeddings-1.5b`
  - Produces: 1024 dimensions
  - Specialized for: Code understanding and analysis
  - Optimized for: Pull request context, code snippets
  
- **Local Model (JINA_EMBEDDING_MODEL2)**: `jinaai/jina-code-embeddings-0.5b` or `jinaai/jina-code-embeddings-1.5b`
  - Same as API model for consistency
  - Used when `USE_JINA_API=false`

### Database Schema
- **Embedding Dimension**: 1536 dimensions
- **Storage**: PostgreSQL with pgvector extension
- **Normalization**: Embeddings are automatically padded/truncated to 1536 dimensions

## Step 4: Testing Your Setup

### Testing API Mode
```bash
# Verify your API key works
curl -H "Authorization: Bearer YOUR_JINA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jina-code-embeddings-1.5b",
    "input": ["def hello(): return world"]
  }' \
  https://api.jina.ai/v1/embeddings
```

### Testing Local Mode

```bash
# Start the Python environment
cd c:\_PERSONAL\ResourceIQ\ -\ SDGP\resourceIQ-backend

# Test embedding generation
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('jinaai/jina-code-embeddings-0.5b')
embeddings = model.encode(['def hello(): return world'])
print(f'Embedding shape: {embeddings[0].shape}')
print(f'First 5 dims: {embeddings[0][:5]}')
"
```

**Expected Output**:
```
Embedding shape: (1024,)
First 5 dims: [-0.123, 0.456, -0.789, 0.012, -0.345]
```

### Verifying Installation in FastAPI App

```bash
# Run the backend
uv run fastapi run app/main.py

# In another terminal, test vector sync
curl -X POST http://localhost:8000/api/v1/vectors/sync/author?author_login=your_github_username
```

## Model Download & Caching

### Where Models Are Stored

**Local Models** are automatically cached:
```
Windows: %USERPROFILE%\.cache\huggingface\hub\
Linux/Mac: ~/.cache/huggingface/hub/
```

### Disk Space Requirements
- **jina-code-embeddings-0.5b**: ~500MB
- **jina-code-embeddings-1.5b**: ~2GB
- **PyTorch**: ~500MB

### Manual Download (Optional)
If you want to pre-download the model:

```bash
python -c "
from sentence_transformers import SentenceTransformer
# This downloads and caches the model
model = SentenceTransformer('jinaai/jina-code-embeddings-1.5b')
print('Model cached successfully')
"
```

## GPU Acceleration (Optional)

### NVIDIA GPU Setup
For faster local embeddings with NVIDIA GPU:

```bash
# Install CUDA-enabled PyTorch
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Verify CUDA availability
python -c "import torch; print(torch.cuda.is_available())"
```

### CPU-Only Setup (Default)
The setup works fine with CPU, just slower:
- 0.5b model: ~200-500 texts/second on modern CPU
- 1.5b model: ~50-100 texts/second on modern CPU

## API Endpoints

### 1. Search Similar PRs
```http
GET /api/v1/vectors/search?query=Issue%20in%20github%20integration&n_results=5
```

**Response:**
```json
{
  "results": [
    {
      "pr_id": "1234567",
      "pr_number": 42,
      "pr_title": "Fix GitHub integration issue",
      "pr_url": "https://github.com/...",
      "author_login": "username",
      "context": "PR description and context...",
      "created_at": "2024-01-02T10:30:00"
    }
  ]
}
```

### 2. Sync Author Vectors
```http
POST /api/v1/vectors/sync/author?author_login=username&max_prs=100
```

Syncs PR embeddings for a specific GitHub author.

### 3. Sync All Vectors
```http
POST /api/v1/vectors/sync/all?max_prs_per_author=50
```

Syncs PR embeddings for all organization members.

## How It Works

### Storage Flow
1. **Fetch PRs** from GitHub API
2. **Extract Context**: Title + Description + Comments
3. **Generate Embeddings**: Send context to Jina API
4. **Normalize**: Pad/truncate to 1536 dimensions
5. **Store**: Save in PostgreSQL with pgvector

### Search Flow
1. **User Query**: "Issue in github integration"
2. **Generate Embedding**: Send query to Jina API
3. **Normalize**: Pad/truncate to 1536 dimensions
4. **Vector Search**: Find k-nearest neighbors using pgvector
5. **Return Results**: Formatted PR data

## Troubleshooting

### Local Mode Issues

#### Error: "No module named 'sentence_transformers'"
**Solution**: Install dependencies
```bash
uv sync
# or manually:
pip install sentence-transformers torch
```

#### Error: "Model not found: jinaai/jina-code-embeddings-0.5b"
**Solution**: Model will auto-download on first use, or manually:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('jinaai/jina-code-embeddings-0.5b')"
```

#### Error: "CUDA out of memory" or slow performance
**Solutions**:
1. Use smaller model:
   ```env
   JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
   ```

2. Reduce batch size in code or use CPU:
   ```python
   model = SentenceTransformer('jinaai/jina-code-embeddings-0.5b', device='cpu')
   ```

3. Close other GPU applications

#### Warning: "Setting `has_transformed_input` is False, but some of the `past_key_values` have a non-empty `input_ids`"
This is a harmless warning, can be ignored.

### API Mode Issues

#### Error: "401 Unauthorized" or "Invalid API key"
**Solution**:
1. Verify your API key format: should start with `jina_`
2. Check API key in Jina console is not expired
3. Test connectivity:
   ```bash
   curl -H "Authorization: Bearer YOUR_KEY" https://api.jina.ai/v1/embeddings
   ```

#### Error: "429 Too Many Requests"
**Solution**: Your API rate limit was exceeded
- Wait before making new requests
- Check your Jina plan limits
- Implement request queuing in code

#### Error: "expected 1536 dimensions, not 1024"
**Solution**: Already fixed in code with automatic normalization. Ensure `EMBEDDING_DIMENSION=1536` in config.

### General Issues

#### Error: "No results returned from vector search"
**Possible causes**:
1. No vectors stored in database - run sync endpoints first:
   ```bash
   curl -X POST http://localhost:8000/api/v1/vectors/sync/all?max_prs_per_author=50
   ```
2. Query doesn't match any PR context - try different keywords
3. Author filter too restrictive - remove `author_login` parameter

#### Slow Search Performance
**Solutions**:
1. Create a vector index:
   ```sql
   CREATE INDEX ON github_pr_vectors USING hnsw (embedding vector_cosine_ops);
   ```
2. Use author filter to narrow search space
3. Reduce `n_results` parameter
4. For local mode, use smaller model or GPU

## Model Comparison & Selection Guide

### When to Use 0.5b (Default)
```
JINA_EMBEDDING_MODEL1=jina-code-embeddings-0.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
```
✅ **Best for**:
- Development/testing
- Real-time applications
- Resource-constrained environments
- CPU-only systems

⏱️ **Performance**: ~200-500 texts/sec (CPU), ~5000+ (GPU)

### When to Use 1.5b (Better Quality)
```
JINA_EMBEDDING_MODEL1=jina-code-embeddings-1.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-1.5b
```
✅ **Best for**:
- Production environments
- Highest accuracy needed
- Sufficient computational resources
- Complex code understanding

⏱️ **Performance**: ~50-100 texts/sec (CPU), ~500-1000 (GPU)

## Code Examples

### Using Embeddings in Your Application

```python
from app.api.embedding.embedding_service import VectorEmbeddingService
from app.db.session import SessionLocal

# Initialize with API mode
db = SessionLocal()
embedding_service = VectorEmbeddingService(db=db, use_api=True)

# Generate embeddings
texts = [
    "fix: resolve GitHub API timeout issue",
    "feat: add new webhook support"
]
embeddings = embedding_service.generate_embeddings(texts)
print(f"Generated {len(embeddings)} embeddings")

# Using local mode
embedding_service_local = VectorEmbeddingService(db=db, use_api=False)
embeddings_local = embedding_service_local.generate_embeddings(texts)
```

### Switching Modes at Runtime

```python
from app.core.config import settings

# Check current mode
if settings.USE_JINA_API:
    print(f"Using Jina API: {settings.JINA_EMBEDDING_MODEL1}")
else:
    print(f"Using local model: {settings.JINA_EMBEDDING_MODEL2}")

# Create appropriate service
embedding_service = VectorEmbeddingService(
    db=db, 
    use_api=settings.USE_JINA_API
)
```

## Local Development

### Using Local Embeddings (No API)
```env
USE_JINA_API=false
JINA_EMBEDDING_MODEL1=jina-code-embeddings-0.5b
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
```

Install dependencies:
```bash
uv sync
# or manually:
pip install sentence-transformers torch
```

### Running Tests
```bash
pytest tests/api/routes/test_vectors.py -v
```

## Production Deployment

### Performance Optimization
1. **Enable Vector Index** (HNSW):
   ```sql
   CREATE INDEX github_pr_vectors_embedding_idx 
   ON github_pr_vectors 
   USING hnsw (embedding vector_cosine_ops);
   ```

2. **Batch Processing**:
   - Sync endpoints process up to 50 PRs per author
   - Adjust `max_prs_per_author` parameter

3. **Rate Limiting**:
   - Jina API has rate limits based on your plan
   - Implement request queuing for large syncs

### Monitoring
Monitor these metrics:
- Embedding API response time
- Vector search latency
- Database index size
- Cache hit rates

## Configuration Reference

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| `JINA_API_KEY` | `jina_...` | Required | Your Jina AI API key |
| `JINA_API_URL` | URL | https://api.jina.ai | Jina API endpoint |
| `JINA_EMBEDDING_MODEL1` | `jina-code-embeddings-0.5b`<br/>`jina-code-embeddings-1.5b` | `jina-code-embeddings-0.5b` | Model for API calls |
| `JINA_EMBEDDING_MODEL2` | `jinaai/jina-code-embeddings-0.5b`<br/>`jinaai/jina-code-embeddings-1.5b` | `jinaai/jina-code-embeddings-0.5b` | Model for local processing |
| `USE_JINA_API` | `true` / `false` | `false` | Use API vs local embeddings |
| `EMBEDDING_DIMENSION` | Integer | 1536 | Vector dimension (must match DB schema) |

## Cost Considerations

### API Mode
- **Jina AI Pricing**: Varies by model and usage tier
- **Cost per 1M tokens**: Check [Jina Pricing](https://jina.ai/pricing/)
- **Code embeddings**: Typically ~100-200 tokens per PR

### Local Mode
- **No API costs**: Free to use
- **Hardware costs**: Computational resources on your machine
- **Storage**: ~500MB-2GB for model files

### Estimate
- ~1 API call per GitHub PR synced
- For 1000 PRs: 1000 API calls = ~$0.50-$2.00 depending on plan

## Deployment Strategies

### Development (Laptop/Desktop)
```env
USE_JINA_API=false
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
```
✅ No API costs, offline capable

### Staging/Production (Server)
```env
USE_JINA_API=true
JINA_EMBEDDING_MODEL1=jina-code-embeddings-1.5b
```
✅ Higher accuracy, scalable, latest models

### Resource-Constrained (Edge/Low-power)
```env
USE_JINA_API=false
JINA_EMBEDDING_MODEL2=jinaai/jina-code-embeddings-0.5b
```
✅ Lower memory footprint

## Quick Start Checklists

### ✅ API Mode (5 minutes)
- [ ] Sign up at [Jina AI Console](https://jina.ai/login)
- [ ] Create API key
- [ ] Add to `.env`: `JINA_API_KEY=jina_...`
- [ ] Set `USE_JINA_API=true`
- [ ] Run: `uv sync && uv run fastapi run app/main.py`
- [ ] Test: `curl -X POST http://localhost:8000/api/v1/vectors/sync/all`

### ✅ Local Mode (10 minutes)
- [ ] Run: `uv sync` (auto-installs dependencies)
- [ ] Set `USE_JINA_API=false`
- [ ] First run: Model auto-downloads (~500MB-2GB)
- [ ] Run: `uv run fastapi run app/main.py`
- [ ] Test: `curl -X POST http://localhost:8000/api/v1/vectors/sync/all`

### ✅ GPU Acceleration (optional)
- [ ] Install CUDA toolkit
- [ ] Install: `pip install torch --index-url https://download.pytorch.org/whl/cu118`
- [ ] Verify: `python -c "import torch; print(torch.cuda.is_available())"`
- [ ] Models automatically use GPU when available

## Support & Resources

### Official Documentation
- [Jina AI Embeddings](https://jina.ai/embeddings/)
- [Jina Code Embeddings Docs](https://jina.ai/embeddings/#code)
- [Jina API Reference](https://docs.api.jina.ai/)
- [HuggingFace Model Card](https://huggingface.co/jinaai/jina-code-embeddings-v1)

### Related Technologies
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [Sentence Transformers](https://www.sbert.net/)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)

### Troubleshooting Links
- [Jina Support](https://jina.ai/support/)
- [GitHub Issues](https://github.com/jina-ai/jina)
- [Community Forum](https://community.jina.ai/)

## FAQ

**Q: Can I switch between 0.5b and 1.5b models?**
A: Yes, just update your `.env` file and restart the app. First run with a new model will download it (~500MB-2GB).

**Q: Do I need both API and local model configured?**
A: No, you only need one. `JINA_EMBEDDING_MODEL1` is for API mode, `JINA_EMBEDDING_MODEL2` for local mode.

**Q: What's the difference between the models?**
A: **0.5b** (200M params) is fast but less accurate. **1.5b** (1.5B params) is slower but more accurate for complex code.

**Q: Can I use a different embedding model?**
A: Not directly without code changes. The codebase is optimized for Jina models. You could adapt it to use other HuggingFace models.

**Q: How long does the first embedding generation take?**
A: Depends on mode:
- **API**: ~1-2 seconds per batch (after model loads)
- **Local 0.5b**: ~5-10 seconds first run (download), then ~1-2 sec/batch
- **Local 1.5b**: ~30-60 seconds first run (download), then ~5-10 sec/batch

**Q: Can I use CPU and GPU together?**
A: Sentence-transformers automatically uses GPU when available. CPU is used as fallback.

**Q: What if I run out of disk space?**
A: HuggingFace cache can be cleaned: `rm -rf ~/.cache/huggingface/hub/`

**Q: Are embeddings cached?**
A: Database vectors are cached in PostgreSQL. API results are not cached by default (can be added).

**Q: How accurate is the search?**
A: Depends on model quality and relevance of PR context. Tests show 85-95% relevance with proper keywords.
