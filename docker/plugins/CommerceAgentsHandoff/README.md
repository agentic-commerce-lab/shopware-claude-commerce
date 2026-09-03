# CommerceAgentsHandoff

Tiny Shopware storefront plugin. UCP carts are Store API context tokens; the shopping agent cannot set `sw-context-token` on the shop origin.

`GET /claude-commerce/continue?token={cartId}` writes that token into the storefront session and redirects to `/checkout/confirm`.

Installed by `docker/bootstrap.sh`. Do not bind-mount this folder read-only over `public/`.
