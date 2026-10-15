# CreatorOS — API Reference

Interactive docs: `http://localhost:8000/docs` (OpenAPI). All endpoints are under `/api`.

## System
| Method | Path | Description |
|---|---|---|
| GET | `/health` | gateway URL, models, mock flag, scheduler state |
| GET | `/platforms` | supported platforms with limits and conventions |
| GET | `/stats` | counts, avg CQS before/after, share of pieces improved by the editor |

## Brands (voice)
| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/brands` | | list |
| POST | `/brands` | `{name, description, samples:[{text, platform}]}` | create; learns the voice if ≥2 samples |
| GET | `/brands/{id}` | | profile + measured stats |
| GET | `/brands/{id}/samples` | | |
| POST | `/brands/{id}/samples` | `{samples:[…], relearn:true}` | add samples, re-learn |
| POST | `/brands/{id}/learn-voice` | | re-learn from current samples |

## Content
| Method | Path | Body / query | Description |
|---|---|---|---|
| POST | `/content?wait=false` | `{brand_id, brief, platforms:[…], scheduled_at?, publish_target?, generate_image?, use_learnings?}` | one piece per platform (campaign); pipeline runs in background (`wait=true` → synchronous) |
| GET | `/content?brand_id&status&limit` | | list |
| GET | `/content/{id}` | | detail: strategy, versions, decisions, performance, quality |
| GET | `/content/{id}/image` | | PNG |
| POST | `/content/{id}/schedule` | `{scheduled_at, publish_target}` | queue |
| POST | `/content/{id}/publish` | | publish now |
| POST | `/content/{id}/performance` | `{impressions, likes, comments, shares, clicks, saves, source, notes}` | record engagement (published pieces only) |
| POST | `/content/{id}/regenerate?wait=false` | | new piece, same brief, current learnings |

## Learning
| Method | Path | Body | Description |
|---|---|---|---|
| POST | `/brands/{id}/learn` | `{platform:"all"|"linkedin"|…}` | run a learning cycle (needs ≥2 published pieces with performance) |
| GET | `/brands/{id}/learnings?include_inactive` | | rules |
| GET | `/brands/{id}/learning-runs` | | runs with feature → engagement tables |

## Decisions
| Method | Path | Query | Description |
|---|---|---|---|
| GET | `/decisions` | `brand_id, content_id, agent, limit` | the auditable trail |

## Ops / demo
| Method | Path | Description |
|---|---|---|
| POST | `/scheduler/run` | publish everything due now |
| POST | `/demo/seed` | create the two demo brands |

### Example

```bash
B=$(curl -s -X POST localhost:8000/api/demo/seed | python -c "import sys,json;print(json.load(sys.stdin)['brands'][0]['id'])")
curl -s -X POST "localhost:8000/api/content?wait=true" -H 'content-type: application/json' \
  -d "{\"brand_id\":\"$B\",\"brief\":\"a LinkedIn post about AI safety\",\"platforms\":[\"linkedin\",\"x\"]}"
```
