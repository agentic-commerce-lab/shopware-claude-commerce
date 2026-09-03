# Storefront web UI

Next.js 16 grid, cart drawer, and assistant rail. Talks to the FastAPI host on port 8004.

```bash
# from repo root, after `npm install`
npm run dev:storefront
```

Opens http://localhost:3005. Catalog warmup on the API fills the grid without a chat turn. Add to cart uses `POST /api/cart/add`. Checkout opens Shopware (`continue_url`) in a new tab — nothing is charged in the agent.

Chat needs `ANTHROPIC_API_KEY`. Search, cart, and checkout work without it.
