---
title: Personal Portfolio Chatbot
---

## The problem this project solves

Recruiters and hiring managers usually only get a resume or a static portfolio page to learn about a candidate, and both are shallow. I built this project to give them a better way to actually talk to me: a chatbot embedded in my personal portfolio site that answers questions about my background, my projects, and my experience, grounded only in documents I've actually written about myself, so anyone curious about me can get real answers instead of skimming a PDF.

## What I'm building, and what's actually running today

This is a retrieval-augmented generation (RAG) chatbot with a FastAPI backend and Postgres with the pgvector extension as the single data store. Retrieval is hybrid: dense embedding search for semantic similarity, plus Postgres full-text search for literal keyword matches, merged with reciprocal rank fusion. Generation runs on open-weight models behind one OpenAI-compatible client, Qwen 3.5 9B locally through Ollama and Llama 3.3 70B on a hosted endpoint in production, rather than the Anthropic or OpenAI APIs. The planned deployment is Fly.io for the backend, Vercel for the frontend, and Neon for Postgres. As of right now, the database and storage layer is built and running. Retrieval, generation, evaluation, and deployment are designed and in active development, not yet fully implemented, so any claim about live retrieval quality or production behavior should be treated as in progress rather than finished.

## The first version, and how it differs from this one

This is the second version of the project. I built the first in June and July 2026 as a conversational question-answering service over my own documents, using the Anthropic API for generation. Its retrieval pipeline was split into an offline indexing step, with PDF extraction, contextual chunking, keyword extraction, and an inverted index, and an online step that answered questions. Instead of embeddings, it ranked chunks with a multi-signal algorithm I designed: token overlap, a keyword boost, phrase matching, and entity-anchor scoring, followed by a diversity rule that allowed at most two chunks per entity. Combining signals was meant to beat any single one on precision. I containerized the backend with Docker and deployed it on AWS ECS Fargate behind a Redis cache, so repeated questions didn't trigger redundant model calls, with GitHub Actions building and pushing images to Amazon ECR on every push and the frontend on Vercel. The current version replaces that ranking with dense embeddings and Postgres full-text search, and the Anthropic API with open-weight models.

## Why I chose open-weight models and hybrid retrieval

I chose open-weight models for generation instead of the Anthropic or OpenAI APIs because I wanted hands-on experience actually running and integrating open-weight models myself, not just calling a hosted API, so I could show prospective employers I've worked with both open and closed model ecosystems. For retrieval, I used hybrid dense-plus-full-text search fused with reciprocal rank fusion instead of relying on vector search alone, so queries get comprehensive coverage: dense embeddings catch results that are semantically close to the query even when the wording differs, and full-text search catches literal keyword matches that embeddings can miss, with reciprocal rank fusion combining the two ranked lists.

## Open engineering decisions I'm still working through

A few things are intentionally unsettled. Cross-encoder reranking on top of the hybrid retrieval is on hold until I have real evaluation numbers comparing retrieval strategies, so I don't add complexity before I know it's earning its keep. I'm also still building the eval harness itself, which is what will actually tell me whether the hybrid approach is outperforming a single-signal baseline in practice. Until that evidence exists, I'm treating the current architecture as a strong starting design rather than a finished, benchmarked system.
