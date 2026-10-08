"""Personas do conselho. LangChain monta o prompt; Gemini fala se houver chave."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

PERSONAS: dict[str, dict[str, str]] = {
    "ceo": {
        "agente": "Estratégia",
        "cargo": "Visão da carteira",
        "prompt": (
            "Você é a mesa de estratégia da Neuro-Quest Capital, uma assessoria de investimentos. "
            "Fale em português claro, em duas a quatro frases, como um assessor explicando a carteira ao cliente. "
            "Traduza o relatório: valor lançado, o que está concentrado e o que isso significa para o risco. "
            "Use somente os números do JSON. Não invente preço de mercado, APY, retorno realizado ou lucro. "
            "Não apresente uma proposta como se já tivesse sido executada."
        ),
    },
    "cio": {
        "agente": "Carteira",
        "cargo": "Propostas",
        "prompt": (
            "Você é a mesa de carteira da Neuro-Quest Capital. "
            "Fale em português claro, em duas a quatro frases, como um gestor explicando propostas ao cliente. "
            "Leia a lista missoes do JSON e diga o que cada proposta busca: reduzir concentração, rebalancear, proteger ou alocar. "
            "Não acrescente ativo, preço ou quantidade que não estejam no relatório. Não prometa retorno."
        ),
    },
    "cco": {
        "agente": "Risco",
        "cargo": "Controle",
        "prompt": (
            "Você é o controle de risco da Neuro-Quest Capital. "
            "Fale em português claro, em duas a quatro frases, como um analista de risco falando com o cliente. "
            "Cite a faixa, o HHI e o peso do maior ativo exatamente como no JSON e explique o que a concentração implica. "
            "Não invente volatilidade, liquidação ou perda que o relatório não mediu."
        ),
    },
}


def _chronicle(persona: str, facts: dict[str, Any]) -> str:
    total = float(facts.get("total_usd") or 0)
    concentration = facts.get("concentracao") or {}
    band = concentration.get("band") or "vazia"
    hhi = float(concentration.get("hhi") or 0)
    top = concentration.get("top_symbol") or "nenhum ativo"
    top_weight = float(concentration.get("top_weight") or 0)
    stable = float(concentration.get("stable_weight") or 0)
    silence = ""
    if facts.get("fonte_numeros") == "contingencia":
        silence = " O motor quantitativo não respondeu; esta leitura usa a contingência da mesa."
    if persona == "ceo":
        return (
            f"A carteira lançada soma {total:.2f} dólares em {facts.get('posicoes', 0)} posições. "
            f"{top} concentra {top_weight:.0%} do valor. "
            f"A concentração está {band}, com HHI {hhi:.2f}.{silence}"
        )
    if persona == "cio":
        missions = facts.get("missoes") or []
        if not missions:
            return (
                "Não há posição lançada, então não há proposta de venda, compra, proteção ou alocação."
                + silence
            )
        joined = " | ".join(missions)
        return f"As propostas da mesa, ainda não executadas: {joined}.{silence}"
    return (
        f"A concentração está {band}. HHI {hhi:.2f}. "
        f"O maior peso é {top}, com {top_weight:.0%} da carteira. "
        f"A parcela estável pesa {stable:.0%}.{silence}"
    )


def narrate(persona: str, facts: dict[str, Any]) -> dict[str, str | None]:
    profile = PERSONAS[persona]
    briefing = json.dumps(facts, ensure_ascii=False)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", profile["prompt"]),
            ("human", "{briefing}"),
        ]
    )
    prompt.invoke({"briefing": briefing})
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        return {"fala": _chronicle(persona, facts), "fonte": "cronica-local", "aviso": None}
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=key, temperature=0.4)
        text = (prompt | llm | StrOutputParser()).invoke({"briefing": briefing}).strip()
        if not text:
            raise RuntimeError("Gemini devolveu texto vazio")
        return {"fala": text, "fonte": "gemini", "aviso": None}
    except Exception:
        return {
            "fala": _chronicle(persona, facts),
            "fonte": "cronica-local",
            "aviso": "O modelo não respondeu. A leitura local manteve os números do relatório.",
        }
