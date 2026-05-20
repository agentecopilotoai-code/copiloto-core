"""``app.chatbot`` — Módulo conversacional de CopilotoIA (TASK-0087).

Contiene exclusivamente el **answer-engine** del chatbot:

  - ``llm_answer.py``     — orquestador local-first (Ollama / fallback cloud).
  - ``cloud_llm_answer.py`` — adapter directo a Claude/OpenAI vía ``httpx``.
  - ``intent_classifier.py`` — clasificador 3-capas (rule → LLM → fallback).

El resto del pipeline conversacional (RAG retrieval, policy engine,
booking, qualification, feedback loop) permanece en ``app.services.*``
porque es **business logic compartida**, no chatbot puro.

TASK-0088 (follow-up, no en alcance de TASK-0087): rewirear este módulo
para que invoque a Ollama/Claude/OpenAI a través de
``app.ai.dispatch(modality='llm', ...)`` en lugar de ``httpx`` directo.
"""
