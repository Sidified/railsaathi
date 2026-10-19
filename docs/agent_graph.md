# RailSaathi Agent Graph (LangGraph)

Max **2 LLM calls** per question. Nodes marked 🤖 call the LLM; all others are plain code.

```mermaid
flowchart TD
    Q(["User question + last 4 chat turns"]) --> C["🤖 classify<br/>LLM call 1 · structured output<br/>intent · language · English query · ticket details"]

    C -->|out_of_scope| REF["refuse<br/>template, no LLM"]
    C -->|rule_question| RET
    C -->|refund_calc| RD{"ticket details<br/>complete?"}
    C -->|tdr| TD{"TDR situation<br/>known?"}

    RD -->|no| ASK["ask_missing<br/>template, no LLM"]
    RD -->|yes| CALC["calculate_refund<br/>tested tool"]
    TD -->|no| ASK
    TD -->|yes| TDR["check_tdr_eligibility<br/>tested tool"]

    CALC --> RET["retrieve<br/>hybrid search · top 5"]
    TDR --> RET

    RET --> GEN["🤖 generate<br/>LLM call 2<br/>answer with [n] citations"]
    GEN --> SC{"self_check<br/>numbers from tools?<br/>citations valid?"}

    SC -->|pass| FIN["finalize<br/>sources + disclaimer"]
    SC -->|fail| FB["fallback<br/>answer built from tool output<br/>no LLM"]

    REF --> E(["END"])
    ASK --> E
    FIN --> E
    FB --> E
```

## LLM calls per path
| Path                        | LLM calls |
| --------------------------- | --------- |
| Out of scope                | 1         |
| Missing details             | 1         |
| Normal answer               | 2         |
| Self-check fails → fallback | 2         |

## Key design choices
- **Classify uses structured output** with the same types as the tools, so it can only produce values the tools accept.
- **Missing details are asked for, never guessed.**
- **Numbers come only from tested tools.** The LLM writes the words; self-check rejects any ₹ amount not found in tool output, user input or a cited source.
- **Fallback instead of retry:** if self-check fails, a deterministic answer is built from the tool output (no 3rd LLM call).
- **No server-side memory:** the client sends the last 4 turns, so no personal details are stored.