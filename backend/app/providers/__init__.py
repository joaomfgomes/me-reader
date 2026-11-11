"""Único sítio com código de fornecedores externos (Azure AI Speech e LLM).

O resto da aplicação fala com interfaces próprias (voz, tutor) e nunca importa SDKs
externos diretamente. Trocar de fornecedor é implementar a interface aqui (ADR-003, ADR-005)."""
