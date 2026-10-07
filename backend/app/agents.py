"""Personas do conselho. LangChain monta o prompt; Gemini fala se houver chave."""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

PERSONAS: dict[str, dict[str, str]] = {
    "ceo": {
        "agente": "Regente do Trono de Circuito",
        "cargo": "CEO",
        "prompt": (
            "Você é o Regente do Trono de Circuito, CEO da Neuro-Quest Capital. "
            "Fale em português, como um personagem de RPG de 16 bits: castelo de silício, "
            "pergaminho de bloco, reino e coroa. Duas a quatro frases. "
            "Use somente os números do relatório JSON. Não invente preço de mercado, APY ou lucro. "
            "Não saia do personagem e não dê conselho de compra como se fosse ordem já executada."
        ),
    },
    "cio": {
        "agente": "Mestre das Missões",
        "cargo": "CIO",
        "prompt": (
            "Você é o Mestre das Missões, CIO da Neuro-Quest Capital. "
            "Fale em português, como um quest giver de RPG de 16 bits misturado com circuitos. "
            "Duas a quatro frases. Leia a lista missoes do JSON e apresente cada uma como missão, "
            "sem acrescentar ativo, preço ou quantidade que não estejam no relatório. "
            "Não prometa vitória nem rendimento."
        ),
    },
    "cco": {
        "agente": "Vigia do Fosso",
        "cargo": "CCO",
        "prompt": (
            "Você é a Vigia do Fosso, CCO da Neuro-Quest Capital. "
            "Fale em português, como sentinela de um RPG de 16 bits: fosso, muralha, runa de risco. "
            "Duas a quatro frases. Cite a faixa, o HHI e o peso do maior ativo exatamente como no JSON. "
            "Não invente volatilidade, liquidação ou ameaça que o relatório não mediu."
        ),
    },
}


def _chronicle(persona: str, facts: dict[str, Any]) -> str:
    total = float(facts.get("total_usd") or 0)
    concentration = facts.get("concentracao") or {}
    band = concentration.get("band") or "vazia"
    hhi = float(concentration.get("hhi") or 0)
    top = concentration.get("top_symbol") or "nenhum estandarte"
    top_weight = float(concentration.get("top_weight") or 0)
    stable = float(concentration.get("stable_weight") or 0)
    silence = ""
    if facts.get("fonte_numeros") == "contingencia":
        silence = " O oráculo quantitativo está em silêncio; estes números são a contingência da mesa."
    if persona == "ceo":
        return (
            f"Regente do Trono de Circuito contempla o reino: {total:.2f} peças de ouro contábil "
            f"em {facts.get('posicoes', 0)} posições. {top} ocupa {top_weight:.0%} do trono "
            f"e a faixa gravada é {band}, HHI {hhi:.2f}.{silence}"
        )
    if persona == "cio":
        missions = facts.get("missoes") or []
        if not missions:
            return (
                "Mestre das Missões enrola o pergaminho vazio. "
                "Sem posições lançadas, não há quest de venda, compra, stop ou pool."
                + silence
            )
        joined = " | ".join(missions)
        return f"Mestre das Missões prega quatro quests no mural: {joined}.{silence}"
    return (
        f"Vigia do Fosso lê a runa: faixa {band}, HHI {hhi:.2f}, "
        f"maior peso {top} a {top_weight:.0%}, caixa estável {stable:.0%}.{silence}"
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
            "aviso": "Gemini não respondeu. A crônica local manteve o personagem e os números do relatório.",
        }
