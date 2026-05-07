# Legacy Import Review Decisions – VP-10

VP-10 resolves the critical Runtime-Tool review gap left by the one-shot legacy import. The legacy import remains a hint source only; Nexusctl stays the source of truth.

## Runtime-tool decisions

| Legacy command | Decision | Capability | Runtime policy |
|---|---|---|---|
| `runtime_tools_list` | resolved | `runtime.tool.invoke` | Registry listing is allowed only through the Nexusctl runtime-tool guardrail boundary. It does not grant concrete tool execution. |
| `runtime_tools_show` | resolved | `runtime.tool.invoke` | Metadata inspection is allowed only through the Nexusctl runtime-tool guardrail boundary. It does not bypass tool capability checks. |
| `runtime_tools_check` | resolved | `runtime.tool.invoke` | Guardrail checks require the runtime-tool invoke capability before concrete tool capability, domain, live-trade and destructive-deny rules are evaluated. |

## Remaining non-runtime manual items

Other imported command names remain non-authoritative review hints. They are not promoted automatically because VP-10 is scoped to runtime tools and imported Runtime-Tool review items.

## Result

- Critical unresolved Runtime-Tool review items: **0**
- Trading agents still cannot invoke software tools.
- Destructive tools remain denied by default.
