# Triage labels

The five canonical roles, label strings equal to their names:

| Label | Meaning |
|---|---|
| `needs-triage` | Not yet assessed. |
| `needs-info` | Blocked on a question only a human can answer. |
| `ready-for-agent` | Fully specified; a worker can take it cold. |
| `ready-for-human` | Requires judgment, a live machine, or an outward-facing decision. |
| `wontfix` | Closed deliberately. |

A measurement run that needs the machine quiet and unthrottled is `ready-for-human`
even when the code is trivial.
