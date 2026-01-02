# Embedding API Setup & Configuration Guide

## Overview
The ResourceIQ backend uses Jina AI embeddings to generate vector embeddings for GitHub PR analysis. This guide covers the complete setup and troubleshooting.

## Prerequisites

### 1. Jina AI API Access
You need a Jina AI API key to use embeddings:

1. Sign up at [Jina AI Console](https://jina.ai/login)
2. Create or obtain your API key
3. Add it to your `.env` file:

```env
JINA_API_KEY=jina_xxxxxxxxxxxxxxxxxxxx
```

### 2. Environment Variables

Add these to your `.env` file:

```env
# Jina AI Configuration
JINA_API_KEY=your_api_key_here
JINA_API_URL=https://api.jina.ai
JINA_EMBEDDING_MODEL1=jina-embeddings-v3
JINA_EMBEDDING_MODEL2=jinaai/jina-embeddings-v3
USE_JINA_API=true
EMBEDDING_DIMENSION=1536
```

## API Models Configuration

### Current Setup
- **API Model**: `jina-embeddings-v3`
  - Produces: 1024 dimensions
  - Best for: General text embeddings
  - Cost: Standard tier
  
- **Local Model**: `jinaai/jina-embeddings-v3`
  - Same as API model for consistency
  - Used when `USE_JINA_API=false`

### Database Schema
- **Embedding Dimension**: 1536 dimensions
- **Storage**: PostgreSQL with pgvector extension
- **Normalization**: Embeddings are automatically padded/truncated to 1536 dimensions

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

### Error: "expected 1536 dimensions, not 896"
**Cause**: Mismatch between generated embeddings and database schema
**Solution**: Already fixed with automatic normalization. Ensure `EMBEDDING_DIMENSION=1536` in config.

### Error: "Invalid API key"
**Solution**:
```bash
# Verify your API key
echo $JINA_API_KEY

# Test API connectivity
curl -H "Authorization: Bearer YOUR_KEY" https://api.jina.ai/v1/embeddings
```

### Error: "No results returned"
**Possible causes**:
1. No vectors stored in database - run sync endpoints first
2. Query doesn't match any PR context - try different keywords
3. Author filter too restrictive - remove `author_login` parameter

### Slow Search Performance
**Solutions**:
1. Create a vector index:
   ```sql
   CREATE INDEX ON github_pr_vectors USING hnsw (embedding vector_cosine_ops);
   ```
2. Use author filter to narrow search space
3. Reduce `n_results` parameter

## Local Development

### Using Local Embeddings (No API)
```env
USE_JINA_API=false
JINA_EMBEDDING_MODEL2=jinaai/jina-embeddings-v3
```

Install dependencies:
```bash
pip install sentence-transformers
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

| Setting | Default | Description |
|---------|---------|-------------|
| `JINA_API_KEY` | Required | Your Jina AI API key |
| `JINA_API_URL` | https://api.jina.ai | Jina API endpoint |
| `JINA_EMBEDDING_MODEL1` | jina-embeddings-v3 | Model for API calls |
| `JINA_EMBEDDING_MODEL2` | jinaai/jina-embeddings-v3 | Model for local processing |
| `USE_JINA_API` | true | Use API vs local |
| `EMBEDDING_DIMENSION` | 1536 | Vector dimension |

## Cost Considerations

- **Jina AI Pricing**: Varies by model and usage tier
- **Database Storage**: pgvector indexes use additional disk space
- **API Calls**: Each PR context generates one embedding request

Estimate: ~1 API call per GitHub PR synced

## Support & Resources

- [Jina AI Documentation](https://jina.ai/docs/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
