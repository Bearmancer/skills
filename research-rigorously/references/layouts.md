# Layout picker

Pick ONE layout per page, from the claim shape. Record the choice in the lesson header. The Layout column lists the `layout` keys `scripts/lesson.py` and `scripts/render.py` accept.

| Claim shape                              | Layout (`layout` key)                              | Mode                             |
| ---------------------------------------- | -------------------------------------------------- | -------------------------------- |
| one mechanism                            | concept                                            | learn, rules, answer, recommend  |
| items with the same attributes           | table                                              | learn, rules, recommend          |
| ordered procedure                        | steps                                              | rules                            |
| dated events                             | timeline                                           | learn                            |
| causal chain                             | cause-effect                                       | learn                            |
| a thing's parts and how they connect     | diagram                                            | learn                            |
| conditions and outcomes                  | decision-tree                                      | rules                            |
| terms                                    | glossary (entries auto-linked)                     | learn, rules                     |
| quick reference                          | cheat-sheet                                        | rules                            |
| question-shaped topic                    | qa, sparingly                                      | learn                            |
| any page                                 | layered wrapper: answer, detail, sources (frame, not a key) | all                     |
| status-bearing claims                    | claim cards (verify renders it; not a key)         | verify                           |

Layered wrapper is the default frame. Direct explanation only; no narrative. Layout and mode choose structure only; neither is printed on the page.
