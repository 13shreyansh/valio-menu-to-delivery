# Valio Aimo: spoken demo script (about 3 minutes)

Live site: https://valio.72.61.22.106.sslip.io. Open it in a fresh window and click "Try the demo account". You get your own clean copy of Hotel Aurora.
**Bold** = what you say. Plain text in brackets = what you do. ★ = a wow moment.

---

## 1. The hook (0:00–0:20)

**"Every Sunday, a head chef turns a menu into a wholesale order. That means 12,643 Valio products, a 5 pm cut-off, and one wrong allergen can put a guest in hospital. We didn't build a chatbot that suggests products. We built an agent a kitchen can trust to spend its money."**

[Landing page on screen. Click "Try the demo account".]

## 2. The prepared week (0:20–0:35)

**"This is Sanna, head chef at Hotel Aurora. Before she has typed a word, Valio has already prepared next week's order from her recipes, her 412 booked guests and her current stock. It covers three deliveries and stays inside her €1,500 weekly limit."**

[Point at the order card and at "This week and month".]

## 3. ★ Wow 1: Valio's own example (0:35–1:05)

**"Let's give it Valio's own challenge, word for word."**

[Ask Valio. Type: "I need 1,000 litres of lactose-free milk by Monday. Find an option that meets our requirements based on price and availability." Send.]

**"It reads the request, then checks live price and stock at Valio for every matching product. About six seconds."**

[The offers appear.]

**"Best, better, good. A thousand litres at €1.01 is €1,010, the lowest price per litre that can actually arrive by Monday. And here's the part that matters: this is bigger than Sanna usually orders, so the agent doesn't just buy it. It asks her first."**

[Point at "1 thing needs your OK".]

## 4. ★ Wow 2: it catches what a tired chef would miss (1:05–1:45)

**"Now something harder. A wedding."**

[Type: "Wedding on Saturday, 120 guests: salmon soup, whitefish with potatoes, lemon tart with almond crust. 4 guests are gluten-free." Send, then click Review order.]

**"One sentence, and it's now 52 checked products. Look at what it noticed by itself:"**

- **"Saturday has no delivery, so it moved everything to Friday."**
- **"Salmon can't arrive in time at Valio, so it proposes trout fillet, same weight, no new allergens."**
- **"The almond crust breaks this kitchen's no-nuts rule, so it left the almonds out and says so."**
- **"And the gluten-free guests: the gluten is in flour the kitchen already has in stock. It's not even on the order, and the agent still found it."**

**"Each of these is a plain decision for Sanna, not a surprise on delivery day."**

[Approve one or two. Click + on one product.]

**"If she changes a quantity after approving, that approval is withdrawn. An OK covers exactly what she saw."**

## 5. Trust: every decision explains itself (1:45–2:05)

[Click "How this was decided". Expand one Details.]

**"Every number traces back to Valio. Here is each live price and stock call, with its time and the raw response. The language model only reads Sanna's words. It never sets a price or a quantity. That's code, and it's logged."**

[Close the panel. Optionally click Place order and show the receipt.]

## 6. ★ Wow 3, the climax: another AI agent orders, and the rules still hold (2:05–2:40)

**"Last thing. Hotel groups have their own purchasing agents. So Valio speaks MCP, the open protocol AI assistants use."**

[In Claude, with the connector from Settings → Connected assistants already added, ask: "Order 2 kg of hazelnuts for Hotel Aurora for Monday."]

**"An outside agent asks for hazelnuts, and gets: 'your rule is no nuts.' Same rules, same limits, same log as the chef. An outside agent can prepare and place orders within the rules, but it can never approve for the chef. That's what makes it a trusted trade agent, not just an agent."**

[If there's time, ask Claude: "Order 1,000 litres of lactose-free milk by Monday." It comes back as needs_approval with a review link. Open Orders in the portal and show it waiting for Sanna.]

## 7. Close (2:40–3:00)

**"We stress-tested it live this morning: ten users at once plus three outside agents, 220 steps, zero errors. It's running now, and every visitor gets their own private copy. Your kitchen plans. Valio orders."**

---

## If someone asks "what surprised you?" (true stories from this build)

- **Valio's own API pushed back.** Under real load, Valio's price service started rate-limiting us, and the site showed "Valio is unavailable". We built a shared queue with retries, and the site now reuses an answer from the last 30 minutes, logged as such. Then we stress-tested it again: zero errors.
- **Suppliers leave the allergen field empty.** A 1 kg bag of hazelnuts was declared as containing no allergens. Now the agent also reads product names, so "hasselpähkinä" counts as nuts, and undeclared products in risky categories need a person's OK.
- **The second wedding cost €0.** Once a week was already ordered, a new event "used" stock bought for an earlier one. We found it with an independent AI judge, fixed it, and added a regression test.
- **How we worked:** an AI judge that had never seen our code scored us. We fixed every finding, then broke the site with 10 simultaneous users and fixed what broke.

## Safety notes for recording

- Don't say a fixed total for the wedding. It depends on live Valio stock. Read what's on screen.
- Milk by Monday only works before Valio's Sunday 17:00 order-by time.
- The MCP connector needs this copy's token. Copy the connector address from Settings → Connected assistants in the same browser session you're recording in.
