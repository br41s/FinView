"""The one rule every prompt that produces user-visible text must carry.

FinView shows data; it does not advise. The UI says so next to every
machine-generated text, but a notice does not undo a model that writes "buy X":
the output itself has to stay descriptive. Each prompt had its own partial
version of this rule — the cycle report had it, the per-ticker report asked for
position sizing, and the chat, which is given the user's own positions, had
none. `test_llm_rules.py` asserts every user-facing prompt includes it.
"""

NOT_ADVICE_RULE_ES = (
    "FinView es una herramienta de datos, no un asesor. Describe lo que muestran los datos; "
    "NUNCA recomiendes comprar, vender ni mantener, ni digas cuánto invertir, qué tamaño de "
    "posición tomar o qué debería hacer el lector. Si te piden un consejo o una recomendación, "
    "responde que FinView no presta asesoramiento financiero y que la decisión es del usuario, "
    "y ofrece los datos relevantes."
)

NOT_ADVICE_RULE_EN = (
    "FinView is a data tool, not an adviser. Every text field must describe the mechanism "
    "(what happens, what price it tends to move, and why); it must NEVER tell the reader to "
    "buy, sell or hold, suggest a position size, or say what they should do."
)
