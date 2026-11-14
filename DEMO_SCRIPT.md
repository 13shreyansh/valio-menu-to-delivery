# Valio Aimo recording, two minutes

Use https://valio-menu-to-delivery.vercel.app in a fresh browser session. All steps below are real actions. Do not speed through unfinished lookups or add cards in editing. Prices, products and totals may change. Read the current screen rather than quoting the example figures from the design spec.

| Time | Action and narration |
| --- | --- |
| 0:00–0:12 | Kitchen still. “Sanna runs Hotel Aurora's kitchen. Her menu and bookings are already connected. A Saturday wedding just landed, with 120 guests.” |
| 0:12–0:27 | Click “Try the demo account (Hotel Aurora)”. Show the dashboard's already prepared weekly order, deliveries and budget. “Valio has prepared the routine week from her recipes, bookings and stock.” |
| 0:27–0:52 | Click Ask Valio. Tap the microphone, speak “Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart.” Tap again to stop. Check the real transcript and click Send. Typed fallback: enter the same words and click Send. Let the real checklist finish. Close Ask Valio. “She says dishes and guests. Valio checks the ingredients, supply, packs, allergens and budget.” |
| 0:52–1:25 | Click Review order. Show the three actual decisions. Approve each. Increase Friday cream by one pack with +. Show the reopened pack and budget approvals, then approve them again. Open Why? on that product, then close it. Open How this was decided, expand a real call's Details, then close it. Open Settings → Ordering rules. Return through Dashboard → Review order. Click Place order. Show the confirmation, including its small demo-account notice. |
| 1:25–1:50 | In a real Claude chat with the custom connector already added, ask “Order breakfast for 40 for Hotel Aurora's Wednesday conference.” Let Claude call the real MCP tools and return the order number. Back in the portal, open Orders and show that exact number, “Placed by Aurora Group assistant” and “Within your rules”. Do not replace this clip with a simulated chat. |
| 1:50–2:00 | Return to Dashboard. End narration: “Your kitchen plans. Valio orders.” |

The exact MCP address and setup steps are in Settings → Connected assistants:
https://valio-menu-to-delivery.vercel.app/mcp/

The demo account has no MCP authentication. Its connector can access only Hotel Aurora's synthetic account. It cannot impersonate a chef approval. The sponsor supplies no order API; Place order stores a confirmation in our app.

Photo inputs, if needed for a separate recording, are at the unlinked /samples page. A photo must be uploaded and sent by the recorder. No request is prefilled and no event appears by itself.

The headless acceptance flow is `npx playwright test`. It types the request, performs all approvals and the quantity edit, opens the receipt and settings, places the order, then runs the outside HTTPS MCP client and verifies the resulting account order. This does not verify a physical microphone or a real Claude connector chat. Record those two interactions only after checking them live.
