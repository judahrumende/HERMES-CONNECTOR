# Design QA — Hermes command centre

## Sources and viewports

| State | Reference | Implementation | Viewport |
|---|---|---|---|
| Mobile home | `codex-clipboard-31a87496-6413-4f48-87e9-2c9d11a0ce5f.png` | `.impeccable/review/mobile.png` | 322 × 697 capture |
| Mobile CEO thread | `codex-clipboard-63bc07bc-f291-4ba1-b619-b1615ef6685f.png` | `.impeccable/review/mobile-thread.png` | 322 × 697 capture |
| Desktop command centre | Product-adapted expansion of the mobile references | `.impeccable/review/desktop.png` | 1190 × 744 capture |

## Comparison history

1. The first implementation pass matched the reference hierarchy: circular identities, quiet white canvas, light dividers, conversation-first rows, orange agent identity, centered system messages, and a persistent composer.
2. Mobile interaction inspection found the composer extending beneath the fixed bottom navigation. The thread was also carrying a redundant app-level header above its conversation header.
3. The mobile layout was corrected by giving the app view an explicit flex basis, increasing the thread viewport when its app header is hidden, and routing the thread back button to the conversation home.
4. Final side-by-side composites were generated at `.impeccable/review/home-comparison.png` and `.impeccable/review/thread-comparison.png`.
5. The independent finish review returned `PASS WITH NOTES`. Its density, low-contrast metadata, and mobile safe-area findings were addressed in one batch. The verdict pass marked those three findings resolved and returned a final disposition of `PASS`; desktop/mobile stylistic convergence remains partial, and orange intentionally continues to identify both agents and their capability action as specified by the supplied Convos system.

## Functional checks

- Landing page code and styling were not modified.
- Desktop and mobile command-centre navigation render without horizontal overflow.
- Agent selection opens the correct CEO thread.
- Thread back navigation returns to the conversation home.
- Composer input enables Send only when non-empty; media actions remain disabled with configuration explanations.
- Offline/local-only state does not create simulated agent replies.
- Production build and strict TypeScript checks pass.
- The repository has no Vitest test files; `npm test` reports that condition instead of executing a suite.

## Result

Passed for the requested visual and interaction scope. The implementation deliberately adapts rather than clones social-only details such as QR invitations, because Hermes agents are persistent organisational roles controlled by the operator.
